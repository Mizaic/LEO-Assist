"""Patient-level rollup SBAR orchestrator.

Atlas trace:
  DI: DI-CC0BD732 (per-episode SBAR + patient rollup)

Aggregates all per-episode :Assessment nodes for a patient into ONE
patient-level rollup :Assessment that reasons across episodes (e.g.
sequencing of urgent referrals, contraindications between treatments,
shared safety-netting). The rollup uses the dedicated
``sbar_rollup_recommendation_v1`` prompt and is tagged with
``assessment_scope='rollup'`` so the UI can distinguish it from the
per-episode summaries it draws from.

The rollup explicitly does NOT regenerate Situation/Background --
those are derived deterministically by concatenating the per-episode
sections with episode headers. Only the Recommendation requires an
LLM call.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from libs.cypher.sbar_assessment_queries import (
    CREATE_ASSESSMENT,
    FINALISE_ASSESSMENT,
    LIST_PATIENT_EPISODE_ASSESSMENTS,
    SET_ASSESSMENT_NARRATIVE,
    SET_BACKGROUND,
    SET_RECOMMENDATION,
    SET_SITUATION,
)

from .sbar_orchestrator import SBAROrchestrator

logger = logging.getLogger(__name__)


SET_ASSESSMENT_SCOPE_ROLLUP = """
MATCH (a:Assessment {id: $assessment_id})
SET a.assessment_scope = 'rollup',
    a.updated_at       = datetime()
RETURN a.id AS id
"""


# Default rollup prompt caller -- a thin async wrapper around the
# existing recommendation invoke pattern. Tests inject a fake.
RollupCaller = Callable[[list[dict[str, Any]]], "RollupResult"]


@dataclass(frozen=True)
class RollupResult:
    markdown: str
    actions: tuple[dict[str, Any], ...]
    citations: tuple[dict[str, Any], ...] = ()
    missing: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatientRollupRequest:
    run_id: str
    patient_id: str
    requested_by: str | None = None
    tenant_id: str | None = None


@dataclass(frozen=True)
class PatientRollupResponse:
    assessment_id: str
    status: str
    episode_count: int
    rollup_markdown: str
    actions: tuple[dict[str, Any], ...]
    duration_s: float


class PatientRollupSBAROrchestrator:
    def __init__(
        self,
        *,
        patient_graph_client: Any | None = None,
        rollup_caller: RollupCaller | None = None,
    ) -> None:
        self._client = patient_graph_client
        self._call_rollup = rollup_caller or _default_rollup_caller

    async def run(self, req: PatientRollupRequest) -> PatientRollupResponse:
        started = time.time()
        client = self._client_or_default()
        assessment_id = uuid.uuid4().hex

        with client.session() as session:
            episodes = self._load_episode_assessments(session, req.patient_id)

        self._create_draft(client, req, assessment_id)
        SBAROrchestrator._run_cypher(
            client, SET_ASSESSMENT_SCOPE_ROLLUP, assessment_id=assessment_id
        )

        situation_md = self._compose_situation(episodes)
        background_md = self._compose_background(episodes)
        assessment_md = self._compose_assessment(episodes)

        SBAROrchestrator._run_cypher(
            client,
            SET_SITUATION,
            assessment_id=assessment_id,
            situation=situation_md,
        )
        SBAROrchestrator._run_cypher(
            client,
            SET_BACKGROUND,
            assessment_id=assessment_id,
            background=background_md,
            background_parts=json.dumps([]),
        )
        SBAROrchestrator._run_cypher(
            client,
            SET_ASSESSMENT_NARRATIVE,
            assessment_id=assessment_id,
            assessment=assessment_md,
            assessment_codes=[],
            assessment_rules=json.dumps([]),
        )

        try:
            rollup = await self._call_rollup(episodes)
        except Exception as exc:
            logger.exception("Rollup recommendation call failed")
            rollup = RollupResult(
                markdown=(f"_Rollup recommendation unavailable: {exc!s}_"),
                actions=(),
            )

        SBAROrchestrator._run_cypher(
            client,
            SET_RECOMMENDATION,
            assessment_id=assessment_id,
            recommendation=rollup.markdown,
            recommendation_actions=json.dumps(list(rollup.actions)),
        )

        content = self._compose_markdown(
            situation_md, background_md, assessment_md, rollup.markdown
        )
        status = "completed" if episodes else "draft"
        SBAROrchestrator._run_cypher(
            client,
            FINALISE_ASSESSMENT,
            assessment_id=assessment_id,
            content=content,
            status=status,
            errors=[],
            stt=None,
            stt_evidence=None,
            alternative_pathway=None,
            alternative_pathway_evidence=None,
            rtr=None,
            rtr_evidence=None,
        )

        duration = time.time() - started
        return PatientRollupResponse(
            assessment_id=assessment_id,
            status=status,
            episode_count=len(episodes),
            rollup_markdown=rollup.markdown,
            actions=rollup.actions,
            duration_s=duration,
        )

    @staticmethod
    def _load_episode_assessments(
        session, patient_id: str
    ) -> list[dict[str, Any]]:
        try:
            result = session.run(
                LIST_PATIENT_EPISODE_ASSESSMENTS, patient_id=patient_id
            )
            rows = list(result) if result is not None else []
        except Exception:
            logger.exception(
                "Failed to load episode assessments for patient %s", patient_id
            )
            return []
        return [dict(r) for r in rows]

    @staticmethod
    def _create_draft(
        client, req: PatientRollupRequest, assessment_id: str
    ) -> None:
        SBAROrchestrator._run_cypher(
            client,
            CREATE_ASSESSMENT,
            patient_id=req.patient_id,
            assessment_id=assessment_id,
            run_id=req.run_id,
            requested_by=req.requested_by,
            tenant_id=req.tenant_id,
            guideline_ids=[],
        )

    @staticmethod
    def _compose_situation(episodes: list[dict[str, Any]]) -> str:
        if not episodes:
            return "_No active episodes._"
        parts = ["# Patient situation across episodes\n"]
        for ep in episodes:
            parts.append(
                f"## Episode {ep.get('episode_id', 'unknown')}\n\n"
                f"{ep.get('situation') or '_No situation summary._'}\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _compose_background(episodes: list[dict[str, Any]]) -> str:
        if not episodes:
            return "_No active episodes._"
        parts = ["# Patient background across episodes\n"]
        for ep in episodes:
            parts.append(
                f"## Episode {ep.get('episode_id', 'unknown')}\n\n"
                f"{ep.get('background') or '_No background summary._'}\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _compose_assessment(episodes: list[dict[str, Any]]) -> str:
        if not episodes:
            return "_No active episodes._"
        parts = ["# Patient assessment across episodes\n"]
        for ep in episodes:
            parts.append(
                f"## Episode {ep.get('episode_id', 'unknown')}\n\n"
                f"{ep.get('assessment') or '_No assessment summary._'}\n"
            )
        return "\n".join(parts)

    @staticmethod
    def _compose_markdown(
        situation: str, background: str, assessment: str, recommendation: str
    ) -> str:
        return (
            "# Patient Rollup SBAR\n\n"
            "## Situation\n\n" + situation + "\n\n"
            "## Background\n\n" + background + "\n\n"
            "## Assessment\n\n" + assessment + "\n\n"
            "## Recommendation\n\n" + (recommendation or "_Not generated._")
        )

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        from libs.neo4j_client.client import PatientGraphClient

        return PatientGraphClient()


async def _default_rollup_caller(
    episodes: list[dict[str, Any]],
) -> RollupResult:
    """Default rollup caller -- returns a placeholder.

    The real implementation will live in libs.sbar.prompt_calls and
    use the sbar_rollup_recommendation_v1 prompt. We keep the default
    intentionally inert so unit tests do not require live LLM access;
    integration tests inject a real caller.
    """
    if not episodes:
        return RollupResult(
            markdown="No active episodes require a cross-episode recommendation.",
            actions=(),
        )
    return RollupResult(
        markdown=(
            "_Rollup recommendation prompt not yet wired up. "
            f"{len(episodes)} episodes available for cross-episode review._"
        ),
        actions=(),
    )
