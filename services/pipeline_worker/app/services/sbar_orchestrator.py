"""End-to-end orchestrator for an SBAR generation job.

Triggered from the pipeline-jobs queue with event_type='sbar_requested'.
Persists the :Assessment incrementally so a partial Assessment is
recoverable if a later stage fails. Publishes progress events to Redis
pub/sub channel ``pipeline:{run_id}`` so the UI can render a live
status.

See DI-LEO-AI-186, DI-LEO-AI-188, DI-LEO-AI-189.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from libs.cypher.sbar_assessment_queries import (
    CREATE_ASSESSMENT,
    FINALISE_ASSESSMENT,
    LINK_ASSESSMENT_TO_ENCOUNTER,
    LINK_ASSESSMENT_TO_PROCEDURE_REQUEST,
    LINK_ASSESSMENT_TO_REFERRAL_REQUEST,
    SET_ASSESSMENT_NARRATIVE,
    SET_BACKGROUND,
    SET_RECOMMENDATION,
    SET_SITUATION,
)
from libs.sbar.assessment_formatter import (
    AssessmentNarrative,
    evaluate_codes_against_guidelines,
    format_assessment,
)
from libs.sbar.events import (
    SBARRequestPayload,
    SituationArtifactType,
)
from libs.sbar.prompt_calls import (
    call_background,
    call_recommendation,
    call_situation,
)
from libs.sbar.source_resolver import (
    aggregate_codes,
    resolve_background_sources,
    resolve_situation,
)

logger = logging.getLogger(__name__)


ProgressPublisher = Callable[[str, dict[str, Any]], None]


def _default_publisher() -> ProgressPublisher:
    from services.coding_worker.app.services.progress_publisher import (
        publish_progress,
    )

    return publish_progress


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class SBARResult:
    assessment_id: str
    status: str
    situation: str
    background: str
    assessment: str
    recommendation: str
    content: str
    actions: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    pathway_hints: dict[str, Any]
    errors: list[str]
    duration_s: float


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class SBAROrchestrator:
    """One-shot orchestrator. Construct, then call ``.run(payload)``.

    Dependencies are injected so tests can substitute fakes for the
    Patient Graph client, the LLM invoker, and the progress publisher.
    """

    def __init__(
        self,
        *,
        patient_graph_client: Any | None = None,
        publish_progress: ProgressPublisher | None = None,
        situation_caller=call_situation,
        background_caller=call_background,
        recommendation_caller=call_recommendation,
        evaluator=evaluate_codes_against_guidelines,
        formatter=format_assessment,
    ) -> None:
        self._client = patient_graph_client
        self._publish = publish_progress or _default_publisher()
        self._call_situation = situation_caller
        self._call_background = background_caller
        self._call_recommendation = recommendation_caller
        self._evaluate = evaluator
        self._format = formatter

    # -- public --------------------------------------------------------

    async def run(self, payload: SBARRequestPayload) -> SBARResult:
        """Execute all four SBAR stages and persist the Assessment."""
        run_id = payload.run_id
        assessment_id = payload.assessment_id or uuid.uuid4().hex
        started = time.time()
        errors: list[str] = []

        self._emit(run_id, "sbar_started", {
            "assessment_id": assessment_id,
            "patient_id": payload.situation.patient_id,
        })

        client = self._client_or_default()

        # Persist a draft Assessment up-front so the UI can poll for it.
        with client.session() as session:
            self._create_draft(session, payload, assessment_id)
            self._link_artefacts(session, payload, assessment_id)

            # -- Stage 1: Situation --------------------------------------
            resolved_situation = resolve_situation(session, payload.situation)
            self._emit(run_id, "sbar_stage_started", {
                "stage": "situation",
                "assessment_id": assessment_id,
            })
            try:
                sit_result = await self._call_situation(
                    resolved_situation,
                    extra_context={
                        "guideline_ids": payload.guideline_ids,
                        "concern": (payload.concern or "").strip() or None,
                    },
                    patient_id=payload.situation.patient_id,
                )
            except Exception as exc:
                logger.exception("SBAR situation call failed")
                sit_result = {"markdown": "", "raw": {}, "error": str(exc)}
            situation_md = sit_result.get("markdown") or ""
            if sit_result.get("error"):
                errors.append(f"situation:{sit_result['error']}")
            session.run(
                SET_SITUATION,
                assessment_id=assessment_id,
                situation=situation_md,
            )
            self._emit(run_id, "sbar_stage_completed", {
                "stage": "situation",
                "assessment_id": assessment_id,
                "preview": _preview(situation_md),
            })

            # -- Stage 2: Background -------------------------------------
            resolved_sources = resolve_background_sources(
                session, payload.background
            )
            aggregated = aggregate_codes(resolved_sources)
            self._emit(run_id, "sbar_stage_started", {
                "stage": "background",
                "assessment_id": assessment_id,
                "source_count": len(resolved_sources),
                "code_count": len(aggregated),
            })
            try:
                bg_result = await self._call_background(
                    resolved_sources,
                    aggregated,
                    referring_specialty=_first_specialty(resolved_situation),
                    patient_id=payload.situation.patient_id,
                )
            except Exception as exc:
                logger.exception("SBAR background call failed")
                bg_result = {"markdown": "", "raw": {}, "error": str(exc)}
            background_md = bg_result.get("markdown") or ""
            if bg_result.get("error"):
                errors.append(f"background:{bg_result['error']}")
            session.run(
                SET_BACKGROUND,
                assessment_id=assessment_id,
                background=background_md,
            )
            self._emit(run_id, "sbar_stage_completed", {
                "stage": "background",
                "assessment_id": assessment_id,
                "preview": _preview(background_md),
            })

            # -- Stage 3: Assessment (deterministic) ----------------------
            self._emit(run_id, "sbar_stage_started", {
                "stage": "assessment",
                "assessment_id": assessment_id,
            })
            patient_codes = sorted({c.concept_id for c in aggregated})
            try:
                eval_payload = self._evaluate(
                    patient_codes=patient_codes,
                    guideline_ids=payload.guideline_ids or None,
                )
                narrative: AssessmentNarrative = self._format(
                    matched_rules=eval_payload.get("matched_rules") or [],
                    patient_codes=patient_codes,
                    guideline_ids=payload.guideline_ids or None,
                )
            except Exception as exc:
                logger.exception("SBAR assessment formatter failed")
                errors.append(f"assessment:{exc}")
                narrative = AssessmentNarrative(
                    markdown="_Assessment unavailable due to evaluator error._",
                    rules=[],
                    codes=patient_codes,
                    pathway_hints={
                        "stt": None, "stt_evidence": None,
                        "alternative_pathway": None,
                        "alternative_pathway_evidence": None,
                        "rtr": "no", "rtr_evidence": str(exc),
                    },
                )
            session.run(
                SET_ASSESSMENT_NARRATIVE,
                assessment_id=assessment_id,
                assessment=narrative.markdown,
                assessment_codes=narrative.codes,
                assessment_rules=json.dumps(narrative.rules),
            )
            self._emit(run_id, "sbar_stage_completed", {
                "stage": "assessment",
                "assessment_id": assessment_id,
                "rule_count": len(narrative.rules),
                "preview": _preview(narrative.markdown),
            })

            # -- Stage 4: Recommendation ---------------------------------
            self._emit(run_id, "sbar_stage_started", {
                "stage": "recommendation",
                "assessment_id": assessment_id,
            })
            guideline_titles = sorted({
                (r.get("guideline_title") or "")
                for r in narrative.rules
                if r.get("guideline_title")
            })
            try:
                rec_result = await self._call_recommendation(
                    situation_md=situation_md,
                    background_md=background_md,
                    assessment_md=narrative.markdown,
                    assessment_rules=narrative.rules,
                    guideline_titles=list(guideline_titles),
                    guidelines=payload.guideline_ids,
                    patient_id=payload.situation.patient_id,
                )
            except Exception as exc:
                logger.exception("SBAR recommendation call failed")
                rec_result = {
                    "markdown": "", "actions": [], "raw": {}, "error": str(exc),
                }
            recommendation_md = rec_result.get("markdown") or ""
            actions = list(rec_result.get("actions") or [])
            if rec_result.get("error"):
                errors.append(f"recommendation:{rec_result['error']}")
            session.run(
                SET_RECOMMENDATION,
                assessment_id=assessment_id,
                recommendation=recommendation_md,
                recommendation_actions=json.dumps(actions),
            )
            self._emit(run_id, "sbar_stage_completed", {
                "stage": "recommendation",
                "assessment_id": assessment_id,
                "action_count": len(actions),
                "preview": _preview(recommendation_md),
            })

            # -- Finalise ------------------------------------------------
            content = _compose_markdown(
                situation_md, background_md, narrative.markdown, recommendation_md
            )
            status = "draft" if errors else "completed"
            hints = narrative.pathway_hints or {}
            session.run(
                FINALISE_ASSESSMENT,
                assessment_id=assessment_id,
                content=content,
                status=status,
                errors=errors,
                stt=hints.get("stt"),
                stt_evidence=hints.get("stt_evidence"),
                alternative_pathway=hints.get("alternative_pathway"),
                alternative_pathway_evidence=hints.get(
                    "alternative_pathway_evidence"
                ),
                rtr=hints.get("rtr"),
                rtr_evidence=hints.get("rtr_evidence"),
            )

        duration = time.time() - started
        self._emit(run_id, "sbar_completed", {
            "assessment_id": assessment_id,
            "status": status,
            "duration_s": round(duration, 3),
            "error_count": len(errors),
        })

        return SBARResult(
            assessment_id=assessment_id,
            status=status,
            situation=situation_md,
            background=background_md,
            assessment=narrative.markdown,
            recommendation=recommendation_md,
            content=content,
            actions=actions,
            rules=narrative.rules,
            pathway_hints=hints,
            errors=errors,
            duration_s=duration,
        )

    # -- internals -----------------------------------------------------

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        # Lazy import keeps test imports cheap.
        from libs.neo4j_client.client import PatientGraphClient

        return PatientGraphClient()

    def _emit(self, run_id: str, event_type: str, body: dict[str, Any]) -> None:
        try:
            payload = {"type": event_type, "run_id": run_id, **body}
            self._publish(run_id, payload)
        except Exception:
            logger.debug("publish_progress failed", exc_info=True)

    def _create_draft(
        self,
        session: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
    ) -> None:
        session.run(
            CREATE_ASSESSMENT,
            patient_id=payload.situation.patient_id,
            assessment_id=assessment_id,
            run_id=payload.run_id,
            requested_by=payload.requested_by,
            tenant_id=payload.tenant_id,
            guideline_ids=payload.guideline_ids,
        )

    def _link_artefacts(
        self,
        session: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
    ) -> None:
        for ref in payload.situation.artifacts:
            try:
                if ref.type is SituationArtifactType.referral_request and ref.id:
                    session.run(
                        LINK_ASSESSMENT_TO_REFERRAL_REQUEST,
                        assessment_id=assessment_id,
                        artifact_id=ref.id,
                    )
                elif ref.type is SituationArtifactType.procedure_request and ref.id:
                    session.run(
                        LINK_ASSESSMENT_TO_PROCEDURE_REQUEST,
                        assessment_id=assessment_id,
                        artifact_id=ref.id,
                    )
            except Exception:
                logger.debug(
                    "link artefact failed for %s/%s",
                    ref.type.value, ref.id, exc_info=True,
                )
        if payload.encounter_id:
            try:
                session.run(
                    LINK_ASSESSMENT_TO_ENCOUNTER,
                    assessment_id=assessment_id,
                    encounter_id=payload.encounter_id,
                )
            except Exception:
                logger.debug(
                    "link encounter %s failed", payload.encounter_id, exc_info=True
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _preview(text: str, max_chars: int = 240) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_chars else text[: max_chars - 1] + "..."


def _first_specialty(resolved) -> str | None:
    for art in resolved.artifacts or []:
        if art.get("type") == SituationArtifactType.referral_request.value:
            spec = art.get("specialty") or ""
            if spec:
                return spec
    return None


def _compose_markdown(
    situation: str, background: str, assessment: str, recommendation: str
) -> str:
    return (
        "# SBAR\n\n"
        "## Situation\n\n" + (situation or "_Not generated._") + "\n\n"
        "## Background\n\n" + (background or "_Not generated._") + "\n\n"
        "## Assessment\n\n" + (assessment or "_Not generated._") + "\n\n"
        "## Recommendation\n\n" + (recommendation or "_Not generated._")
    )


# ---------------------------------------------------------------------------
# Entry point used by the pipeline worker on_message dispatcher
# ---------------------------------------------------------------------------


async def handle_sbar_message(body: dict[str, Any]) -> SBARResult:
    """Dispatch helper used by services/pipeline_worker/app/main.py.

    Validates the body into ``SBARRequestPayload`` and runs the
    orchestrator. Raises ``ValueError`` if the body is malformed so the
    Service Bus consumer can dead-letter the message.
    """
    payload = _coerce_payload(body)
    return await SBAROrchestrator().run(payload)


def _coerce_payload(body: dict[str, Any]) -> SBARRequestPayload:
    """Accept either {context: {...}} (workflow envelope) or a flat body."""
    candidate = body.get("context") if isinstance(body, dict) else None
    if isinstance(candidate, dict) and candidate.get("event_type") == "sbar_requested":
        return SBARRequestPayload.model_validate(candidate)
    if isinstance(body, dict) and body.get("event_type") == "sbar_requested":
        return SBARRequestPayload.model_validate(body)
    raise ValueError("body is not an sbar_requested payload")
