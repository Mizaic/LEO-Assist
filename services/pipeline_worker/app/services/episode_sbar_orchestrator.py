"""Per-episode SBAR orchestrator.

Atlas trace:
  DI: DI-CC0BD732 (Per-episode SBAR with cross-section coherence)

Replaces the patient-level SBAR for clinical use. Instead of producing
ONE summary for the whole patient (which mixed unrelated pathways for
patient 9990001004), we produce ONE SBAR per detected episode of care.
Each per-episode SBAR is scoped to the encounters that belong to that
episode and is linked back to the EpisodeOfCare via HAS_ASSESSMENT.

The orchestrator is intentionally a thin composition over the existing
``SBAROrchestrator``:

1. Build an episode-scoped ``SBARRequestPayload`` from
   :class:`EpisodeSBARRequest`. The Background sources are restricted
   to the episode's encounter_ids and the Situation is given a
   summarisation_context of ``mdt_discussion`` so the prompt knows
   the scope is one care episode.
2. Run the underlying SBAROrchestrator.
3. Tag the resulting :Assessment with ``assessment_scope='episode'``
   and link it to :Episode via HAS_ASSESSMENT.
4. Run the deterministic coherence check
   (``libs.sbar.coherence_check.run_coherence_checks``) and persist
   the flag list onto the Assessment.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from libs.cypher.sbar_assessment_queries import LINK_ASSESSMENT_TO_EPISODE
from libs.sbar.coherence_check import CoherenceFlag, run_coherence_checks
from libs.sbar.events import (
    BackgroundSourceType,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
)

from .sbar_orchestrator import SBARResult, SBAROrchestrator

logger = logging.getLogger(__name__)


SET_ASSESSMENT_COHERENCE_FLAGS = """
MATCH (a:Assessment {id: $assessment_id})
SET a.coherence_flags = $coherence_flags_json,
    a.coherence_severity_max = $severity_max,
    a.updated_at = datetime()
RETURN a.id AS id
"""


@dataclass(frozen=True)
class EpisodeSBARRequest:
    run_id: str
    patient_id: str
    episode_id: str
    encounter_ids: tuple[str, ...]
    suspected_site: str
    canonical_concept_id: str | None = None
    canonical_display_name: str = ""
    requested_by: str | None = None
    tenant_id: str | None = None


@dataclass(frozen=True)
class EpisodeSBARResult:
    episode_id: str
    sbar: SBARResult
    coherence_flags: tuple[CoherenceFlag, ...]


class EpisodeSBAROrchestrator:
    def __init__(
        self,
        *,
        sbar_orchestrator: SBAROrchestrator | None = None,
        patient_graph_client: Any | None = None,
    ) -> None:
        self._inner = sbar_orchestrator or SBAROrchestrator(
            patient_graph_client=patient_graph_client
        )
        self._client = patient_graph_client

    async def run(self, req: EpisodeSBARRequest) -> EpisodeSBARResult:
        if not req.encounter_ids:
            raise ValueError(
                "EpisodeSBAR requires at least one encounter_id; "
                f"episode {req.episode_id} has none"
            )
        payload = self._build_payload(req)
        sbar = await self._inner.run(payload)

        client = self._client_or_default()
        self._link_episode(client, sbar.assessment_id, req.episode_id)
        flags = self._run_coherence(req, sbar)
        self._persist_coherence(client, sbar.assessment_id, flags)

        return EpisodeSBARResult(
            episode_id=req.episode_id,
            sbar=sbar,
            coherence_flags=tuple(flags),
        )

    def _build_payload(self, req: EpisodeSBARRequest) -> SBARRequestPayload:
        return SBARRequestPayload(
            run_id=req.run_id,
            requested_by=req.requested_by,
            tenant_id=req.tenant_id,
            situation=SBARSituationInput(
                patient_id=req.patient_id,
                artifacts=[],
            ),
            background=[
                SBARBackgroundSourceRef(
                    type=BackgroundSourceType.encounter, id=enc_id
                )
                for enc_id in req.encounter_ids
            ],
            assessment_id=uuid.uuid4().hex,
            extra={
                "scope": "episode",
                "episode_id": req.episode_id,
                "suspected_site": req.suspected_site,
                "canonical_concept_id": req.canonical_concept_id,
                "canonical_display_name": req.canonical_display_name,
            },
        )

    @staticmethod
    def _run_coherence(
        req: EpisodeSBARRequest, sbar: SBARResult
    ) -> list[CoherenceFlag]:
        return run_coherence_checks(
            assessment_md=sbar.assessment,
            recommendation_md=sbar.recommendation,
            sbar_markdown=sbar.content,
            canonical_concept_id=req.canonical_concept_id,
            canonical_display_name=req.canonical_display_name,
            suspected_site=req.suspected_site,
        )

    @staticmethod
    def _link_episode(client, assessment_id: str, episode_id: str) -> None:
        try:
            SBAROrchestrator._run_cypher(
                client,
                LINK_ASSESSMENT_TO_EPISODE,
                assessment_id=assessment_id,
                episode_id=episode_id,
            )
        except Exception:
            logger.exception(
                "Failed to link Assessment %s to Episode %s",
                assessment_id,
                episode_id,
            )

    @staticmethod
    def _persist_coherence(
        client, assessment_id: str, flags: list[CoherenceFlag]
    ) -> None:
        severity_rank = {"low": 1, "medium": 2, "high": 3}
        severity_max = "low"
        if flags:
            worst = max(flags, key=lambda f: severity_rank.get(f.severity, 0))
            severity_max = worst.severity
        try:
            SBAROrchestrator._run_cypher(
                client,
                SET_ASSESSMENT_COHERENCE_FLAGS,
                assessment_id=assessment_id,
                coherence_flags_json=json.dumps([f.to_dict() for f in flags]),
                severity_max=severity_max,
            )
        except Exception:
            logger.exception(
                "Failed to persist coherence flags on Assessment %s",
                assessment_id,
            )

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        from libs.neo4j_client.client import PatientGraphClient

        return PatientGraphClient()
