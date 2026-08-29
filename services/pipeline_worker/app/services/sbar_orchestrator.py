"""End-to-end orchestrator for an SBAR generation job.

Atlas trace:
  DO: DO-3CAFDCC3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3CAFDCC3")

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
from datetime import date, datetime, timezone
from typing import Any, Callable

from libs.cypher.sbar_assessment_queries import (
    CREATE_ASSESSMENT,
    FINALISE_ASSESSMENT,
    LINK_ASSESSMENT_TO_ENCOUNTER,
    LINK_ASSESSMENT_TO_PROCEDURE_REQUEST,
    LINK_ASSESSMENT_TO_REFERRAL_REQUEST,
    SET_ASSESSMENT_COMPLIANCE_ALERTS,
    SET_ASSESSMENT_NARRATIVE,
    SET_ASSESSMENT_PROVENANCE,
    SET_ASSESSMENT_USAGE,
    SET_BACKGROUND,
    SET_RECOMMENDATION,
    SET_SITUATION,
    WRITE_SBAR_AUDIT_EVENT,
)
from libs.llm_client.usage_recorder import LLMUsageRecorder
from libs.llm_usage import LLMCostConfig
from libs.sbar.assessment_formatter import (
    AssessmentNarrative,
    evaluate_codes_against_guidelines,
    format_assessment,
)
from libs.sbar.audit_persistence import (
    AuditPersistenceError,
    AuditProvenanceBundle,
    completion_status_from_preconditions,
    validate_completion_preconditions,
)
from libs.sbar.context_integrity import ContextIntegrityResult, validate_sbar_context
from libs.sbar.section_status import integrity_status_for, section_status
from libs.sbar.error_messages import (
    FriendlyError,
    FriendlyNotice,
    background_part_failed_error,
    background_record_split_notice,
    background_split_notice,
    translate_error,
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
from libs.sbar.orchestrator_gate3 import (
    persist_gate3_assessment_fields,
    prepare_gate3_context,
    situation_extra_context,
)
from libs.sbar.pii_guard import strip_dob_citations
from libs.sbar.source_resolver import (
    aggregate_codes,
    resolve_background_sources,
    resolve_situation,
)
from libs.sbar.twow_alert import alert_to_dict, evaluate_twow_mismatch

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
    errors_detail: list[FriendlyError]
    notices: list[FriendlyNotice]
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
        policy_runtime: Any | None = None,
        dry_run: bool = False,
    ) -> None:
        self._client = patient_graph_client
        self._publish = publish_progress or _default_publisher()
        self._call_situation = situation_caller
        self._call_background = background_caller
        self._call_recommendation = recommendation_caller
        self._evaluate = evaluator
        self._format = formatter
        self._policy_runtime = policy_runtime
        self._dry_run = bool(dry_run)

    # -- public --------------------------------------------------------

    async def run(self, payload: SBARRequestPayload) -> SBARResult:
        """Execute all four SBAR stages and persist the Assessment."""
        run_id = payload.run_id
        assessment_id = payload.assessment_id or uuid.uuid4().hex
        started = time.time()
        errors: list[str] = []
        errors_detail: list[FriendlyError] = []
        notices: list[FriendlyNotice] = []

        self._emit(
            run_id,
            "sbar_started",
            {
                "assessment_id": assessment_id,
                "patient_id": payload.situation.patient_id,
            },
        )

        client = self._client_or_default()

        with client.session() as session:
            integrity = validate_sbar_context(session, payload)
        if not integrity.ok:
            return self._fail_context_integrity(
                client=client,
                payload=payload,
                assessment_id=assessment_id,
                run_id=run_id,
                integrity=integrity,
                started=started,
            )

        # DI-LEO-AI-506: every LLM call inside this block flows through
        # invoke_llm_json -> the active recorder, so we accumulate token
        # usage and latency for Situation, Background, and Recommendation
        # in one place.
        #
        # Neo4j sessions are kept short: load graph inputs, then close the
        # session before LLM calls. Writes use client.run() so stale Aura
        # connections retry on a fresh pool connection.
        with LLMUsageRecorder() as usage_recorder:
            self._create_draft(client, payload, assessment_id)
            self._link_artefacts(client, payload, assessment_id)

            # -- Stages 1 + 2: Situation + Background (parallel) ---------
            # Both LLM calls are independent; running them concurrently
            # cuts wall-clock time roughly in half. We resolve the
            # required graph data first (sync), emit the start events,
            # then await both LLM coroutines via asyncio.gather.
            with client.session() as session:
                resolved_situation = resolve_situation(session, payload.situation)
                resolved_sources = resolve_background_sources(
                    session, payload.background
                )
            aggregated = aggregate_codes(resolved_sources)
            extra = dict(payload.extra or {})
            gate3 = await prepare_gate3_context(
                payload=payload,
                resolved_situation=resolved_situation,
                resolved_sources=resolved_sources,
                aggregated=aggregated,
                policy_runtime=self._policy_runtime,
                recall_reason_raw=str(extra.get("referral_reason") or "") or None,
                allowed_chunk_ids=list(extra.get("chunk_ids") or []),
            )
            self._persist_gate3_fields(client, assessment_id, gate3)
            self._persist_twow_mismatch_alert(
                client,
                assessment_id=assessment_id,
                payload=payload,
                resolved_situation=resolved_situation,
                resolved_sources=resolved_sources,
                run_id=run_id,
            )

            self._emit(
                run_id,
                "sbar_stage_started",
                {
                    "stage": "situation",
                    "assessment_id": assessment_id,
                },
            )
            self._emit(
                run_id,
                "sbar_stage_started",
                {
                    "stage": "background",
                    "assessment_id": assessment_id,
                    "source_count": len(resolved_sources),
                    "code_count": len(aggregated),
                },
            )

            def _on_part_progress(event: dict[str, Any]) -> None:
                self._emit(
                    run_id,
                    "sbar_stage_progress",
                    {
                        "stage": "background",
                        "assessment_id": assessment_id,
                        **event,
                    },
                )

            sit_task = self._call_situation(
                resolved_situation,
                extra_context=situation_extra_context(
                    gate3,
                    guideline_ids=payload.guideline_ids,
                    concern=(payload.concern or "").strip() or None,
                ),
                patient_id=payload.situation.patient_id,
                policy_runtime=self._policy_runtime,
            )
            bg_task = self._call_background(
                resolved_sources,
                aggregated,
                referring_specialty=_first_specialty(resolved_situation),
                patient_id=payload.situation.patient_id,
                coverage=gate3.coverage,
                completeness_result=_completeness_from_payload(payload),
                progress_cb=_on_part_progress,
                policy_runtime=self._policy_runtime,
            )
            sit_raw, bg_raw = await asyncio.gather(
                sit_task, bg_task, return_exceptions=True
            )

            if isinstance(sit_raw, Exception):
                logger.exception("SBAR situation call failed", exc_info=sit_raw)
                friendly = translate_error("situation", str(sit_raw))
                sit_result = {
                    "markdown": "",
                    "raw": {},
                    "error": friendly["message"],
                    "error_code": friendly["code"],
                }
            else:
                sit_result = sit_raw
            situation_md = sit_result.get("markdown") or ""
            situation_md, dob_stripped = strip_dob_citations(
                situation_md, resolved_situation.patient_summary.get("birth_date")
            )
            if dob_stripped:
                errors.append("situation:pii_guard_stripped_dob_citation")
            sit_friendly = self._record_stage_error(
                "situation", sit_result, errors, errors_detail
            )
            self._run_cypher(
                client,
                SET_SITUATION,
                assessment_id=assessment_id,
                situation=situation_md,
                situation_status=section_status(
                    text=situation_md,
                    error=(sit_friendly or {}).get("message"),
                ),
            )
            self._emit(
                run_id,
                "sbar_stage_completed",
                {
                    "stage": "situation",
                    "assessment_id": assessment_id,
                    "preview": _preview(situation_md),
                    "error": sit_friendly,
                },
            )

            if isinstance(bg_raw, Exception):
                logger.exception("SBAR background call failed", exc_info=bg_raw)
                friendly = translate_error("background", str(bg_raw))
                bg_result = {
                    "markdown": "",
                    "raw": {},
                    "error": friendly["message"],
                    "error_code": friendly["code"],
                    "parts": [],
                }
            else:
                bg_result = bg_raw
            background_md = bg_result.get("markdown") or ""
            background_md, bg_dob_stripped = strip_dob_citations(
                background_md, resolved_situation.patient_summary.get("birth_date")
            )
            if bg_dob_stripped:
                errors.append("background:pii_guard_stripped_dob_citation")
            bg_friendly = self._record_stage_error(
                "background", bg_result, errors, errors_detail
            )
            bg_notices = self._record_background_notices(bg_result, notices)
            self._record_background_part_errors(bg_result, errors, errors_detail)
            background_parts = list(bg_result.get("parts") or [])
            self._run_cypher(
                client,
                SET_BACKGROUND,
                assessment_id=assessment_id,
                background=background_md,
                background_parts=json.dumps(background_parts),
                background_status=section_status(
                    text=background_md,
                    error=(bg_friendly or {}).get("message"),
                ),
            )
            self._emit(
                run_id,
                "sbar_stage_completed",
                {
                    "stage": "background",
                    "assessment_id": assessment_id,
                    "preview": _preview(background_md),
                    "error": bg_friendly,
                    "notice": bg_notices[0] if bg_notices else None,
                    "notices": bg_notices,
                    "parts": background_parts,
                },
            )

            # -- Stage 3: Assessment (deterministic) ----------------------
            self._emit(
                run_id,
                "sbar_stage_started",
                {
                    "stage": "assessment",
                    "assessment_id": assessment_id,
                },
            )
            # Exclude only definitively ruled-out assertions from rule
            # evaluation. Negated/refuted findings ("no rectal mass",
            # "gallbladder not enlarged") must never trigger positive
            # referral rules. "possible"/"uncertain" findings are
            # deliberately KEPT: NICE safety-netting rules (e.g. NG12
            # 1.2.10 "mass consistent with an enlarged gall bladder") are
            # written to act on exactly this level of clinical certainty
            # -- a GP's hedged exam finding pending confirmatory imaging.
            # Dropping them here would silently suppress the 2WW/urgent
            # referral the guideline exists to trigger. See DI-LEO-AI-189.
            _EXCLUDED_ASSERTIONS = {"absent", "negated", "refuted"}
            eval_codes = sorted(
                {
                    c.concept_id
                    for c in aggregated
                    if _assertion_value(c.assertion) not in _EXCLUDED_ASSERTIONS
                }
            )
            patient_codes = sorted({c.concept_id for c in aggregated})
            demographics = _assessment_demographics(resolved_situation.patient_summary)
            extra = dict(payload.extra or {})
            compliance_result = extra.get("compliance_result")
            try:
                if isinstance(compliance_result, dict) and (
                    compliance_result.get("primary")
                    or compliance_result.get("alternatives")
                ):
                    from libs.sbar.spoa_disposition import derive_spoa_disposition

                    primary_rules = list(
                        (compliance_result.get("primary") or {}).get("matched_rules")
                        or compliance_result.get("matched_rules")
                        or []
                    )
                    alternative_rules = list(
                        (compliance_result.get("alternatives") or {}).get(
                            "matched_rules"
                        )
                        or []
                    )
                    spoa_code, spoa_evidence = derive_spoa_disposition(
                        primary_rules=primary_rules,
                        alternative_rules=alternative_rules,
                        source_node_type=str(extra.get("source_node_type") or ""),
                        healthcare_service_spoa_id=str(
                            extra.get("healthcare_service_spoa_id") or ""
                        )
                        or None,
                        reason_context={
                            "completeness_result": extra.get("completeness_result"),
                            "referral_reason": extra.get("referral_reason"),
                            "entities": extra.get("entities"),
                            "section_hits": extra.get("section_hits"),
                            "form_clinical_section": extra.get(
                                "form_clinical_section"
                            ),
                        },
                    )
                    if spoa_code == "further_information_required":
                        primary_rules = []
                        alternative_rules = []
                    narrative: AssessmentNarrative = self._format(
                        matched_rules=primary_rules,
                        patient_codes=patient_codes,
                        guideline_ids=payload.guideline_ids or None,
                        compliance_context=compliance_result,
                        spoa_disposition=spoa_code,
                        spoa_disposition_evidence=spoa_evidence,
                    )
                else:
                    eval_payload = await self._evaluate(
                        patient_codes=eval_codes,
                        guideline_ids=payload.guideline_ids or None,
                        patient_age=demographics.get("patient_age"),
                        patient_sex=demographics.get("patient_sex"),
                    )
                    narrative = self._format(
                        matched_rules=eval_payload.get("matched_rules") or [],
                        patient_codes=patient_codes,
                        guideline_ids=payload.guideline_ids or None,
                    )
            except Exception as exc:
                logger.exception("SBAR assessment formatter failed")
                friendly = translate_error("assessment", str(exc))
                errors.append(f"assessment:{friendly['message']}")
                errors_detail.append(friendly)
                narrative = AssessmentNarrative(
                    markdown="_Assessment unavailable due to evaluator error._",
                    rules=[],
                    codes=patient_codes,
                    pathway_hints={
                        "stt": None,
                        "stt_evidence": None,
                        "alternative_pathway": None,
                        "alternative_pathway_evidence": None,
                        "rtr": "no",
                        "rtr_evidence": str(exc),
                    },
                )
            self._run_cypher(
                client,
                SET_ASSESSMENT_NARRATIVE,
                assessment_id=assessment_id,
                assessment=narrative.markdown,
                assessment_codes=narrative.codes,
                assessment_rules=json.dumps(narrative.rules),
                assessment_status=section_status(
                    text=narrative.markdown,
                    error=next(
                        (e for e in errors if str(e).startswith("assessment:")),
                        None,
                    ),
                ),
            )
            self._emit(
                run_id,
                "sbar_stage_completed",
                {
                    "stage": "assessment",
                    "assessment_id": assessment_id,
                    "rule_count": len(narrative.rules),
                    "preview": _preview(narrative.markdown),
                },
            )

            # -- Stage 4: Recommendation ---------------------------------
            self._emit(
                run_id,
                "sbar_stage_started",
                {
                    "stage": "recommendation",
                    "assessment_id": assessment_id,
                },
            )
            guideline_titles = sorted(
                {
                    (r.get("guideline_title") or "")
                    for r in narrative.rules
                    if r.get("guideline_title")
                }
            )
            try:
                rec_result = await self._call_recommendation(
                    situation_md=situation_md,
                    background_md=background_md,
                    assessment_md=narrative.markdown,
                    assessment_rules=narrative.rules,
                    guideline_titles=list(guideline_titles),
                    guidelines=payload.guideline_ids,
                    patient_id=payload.situation.patient_id,
                    policy_runtime=self._policy_runtime,
                    spoa_disposition=narrative.spoa_disposition,
                    spoa_disposition_evidence=narrative.spoa_disposition_evidence,
                )
            except Exception as exc:
                logger.exception("SBAR recommendation call failed")
                friendly = translate_error("recommendation", str(exc))
                rec_result = {
                    "markdown": "",
                    "actions": [],
                    "raw": {},
                    "error": friendly["message"],
                    "error_code": friendly["code"],
                }
            recommendation_md = rec_result.get("markdown") or ""
            recommendation_md, rec_dob_stripped = strip_dob_citations(
                recommendation_md, resolved_situation.patient_summary.get("birth_date")
            )
            if rec_dob_stripped:
                errors.append("recommendation:pii_guard_stripped_dob_citation")
            if narrative.spoa_disposition:
                from libs.sbar.spoa_disposition import (
                    prepend_spoa_disposition_to_recommendation,
                )

                recommendation_md = prepend_spoa_disposition_to_recommendation(
                    recommendation_md,
                    narrative.spoa_disposition,
                    narrative.spoa_disposition_evidence,
                )
            actions = list(rec_result.get("actions") or [])
            rec_friendly = self._record_stage_error(
                "recommendation", rec_result, errors, errors_detail
            )
            self._run_cypher(
                client,
                SET_RECOMMENDATION,
                assessment_id=assessment_id,
                recommendation=recommendation_md,
                recommendation_actions=json.dumps(actions),
                recommendation_status=section_status(
                    text=recommendation_md,
                    error=(rec_friendly or {}).get("message"),
                ),
            )
            self._emit(
                run_id,
                "sbar_stage_completed",
                {
                    "stage": "recommendation",
                    "assessment_id": assessment_id,
                    "action_count": len(actions),
                    "preview": _preview(recommendation_md),
                    "error": rec_friendly,
                },
            )

            # -- Finalise ------------------------------------------------
            content = _compose_markdown(
                situation_md, background_md, narrative.markdown, recommendation_md
            )
            hints = narrative.pathway_hints or {}
            audit_event_id = f"audit-{run_id}"
            manifest = (
                dict(self._policy_runtime.execution_manifest)
                if self._policy_runtime is not None
                else {}
            )
            source_accounting = gate3.source_accounting
            audit_bundle = AuditProvenanceBundle(
                execution_manifest=manifest,
                model_provenance=dict(manifest.get("model") or {}),
                source_accounting=source_accounting,
                audit_event_id=audit_event_id,
            )
            try:
                self._persist_mandatory_audit(
                    client=client,
                    payload=payload,
                    assessment_id=assessment_id,
                    run_id=run_id,
                    bundle=audit_bundle,
                    recorder=usage_recorder,
                    duration_s=time.time() - started,
                    stage_errors=errors,
                )
            except AuditPersistenceError as exc:
                errors.append(f"audit:{exc}")
                audit_bundle = AuditProvenanceBundle(
                    execution_manifest=manifest,
                    model_provenance=dict(manifest.get("model") or {}),
                    source_accounting=source_accounting,
                    audit_event_id="",
                )

            status, audit_blockers = completion_status_from_preconditions(
                stage_errors=errors,
                bundle=audit_bundle,
            )
            if audit_blockers:
                for blocker in audit_blockers:
                    if blocker not in errors:
                        errors.append(blocker)

            self._run_cypher(
                client,
                FINALISE_ASSESSMENT,
                assessment_id=assessment_id,
                content=content,
                status=status,
                context_integrity_status=integrity_status_for(
                    audit_blockers=audit_blockers
                ),
                errors=errors,
                stt=hints.get("stt"),
                stt_evidence=hints.get("stt_evidence"),
                alternative_pathway=hints.get("alternative_pathway"),
                alternative_pathway_evidence=hints.get("alternative_pathway_evidence"),
                rtr=hints.get("rtr"),
                rtr_evidence=hints.get("rtr_evidence"),
                spoa_disposition=narrative.spoa_disposition,
                spoa_disposition_evidence=narrative.spoa_disposition_evidence,
            )

            duration = time.time() - started

            # Operational telemetry remains best-effort.
            self._record_usage_telemetry(
                client=client,
                assessment_id=assessment_id,
                run_id=run_id,
                recorder=usage_recorder,
            )

        self._emit(
            run_id,
            "sbar_completed",
            {
                "assessment_id": assessment_id,
                "status": status,
                "duration_s": round(duration, 3),
                "error_count": len(errors),
                "errors": list(errors_detail),
                "notices": list(notices),
            },
        )

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
            errors_detail=list(errors_detail),
            notices=list(notices),
            duration_s=duration,
        )

    # -- internals -----------------------------------------------------

    @staticmethod
    def _record_stage_error(
        stage: str,
        result: dict[str, Any],
        errors: list[str],
        errors_detail: list[FriendlyError],
    ) -> FriendlyError | None:
        """Append a stage error (if any) to both legacy and detail lists.

        Returns the FriendlyError so callers can attach it to the
        matching ``sbar_stage_completed`` SSE event, or ``None`` when
        the stage succeeded.
        """
        message = result.get("error")
        if not message:
            return None
        code = result.get("error_code") or "unknown"
        friendly: FriendlyError = {
            "stage": stage,
            "code": str(code),
            "message": str(message),
        }
        errors.append(f"{stage}:{code}:{message}")
        errors_detail.append(friendly)
        return friendly

    def _persist_twow_mismatch_alert(
        self,
        client: Any,
        *,
        assessment_id: str,
        payload: SBARRequestPayload,
        resolved_situation: Any,
        resolved_sources: list[Any],
        run_id: str,
    ) -> None:
        referral_id = ""
        structured_priority = ""
        for art in resolved_situation.artifacts or []:
            if art.get("type") == SituationArtifactType.referral_request.value:
                referral_id = str(art.get("id") or "")
                structured_priority = str(art.get("priority") or "")
                break
        letter_text = "\n".join(
            str(src.text or "") for src in resolved_sources if (src.text or "").strip()
        )
        alert = evaluate_twow_mismatch(
            structured_priority=structured_priority,
            letter_text=letter_text,
            referral_id=referral_id or payload.run_id,
            run_id=run_id,
        )
        if alert is None:
            return
        try:
            self._run_cypher(
                client,
                SET_ASSESSMENT_COMPLIANCE_ALERTS,
                assessment_id=assessment_id,
                compliance_alerts_json=json.dumps([alert_to_dict(alert)]),
            )
        except Exception:
            logger.warning(
                "SBAR twow alert: failed to persist for assessment %s",
                assessment_id,
                exc_info=True,
            )

    @staticmethod
    def _record_background_notices(
        result: dict[str, Any],
        notices: list[FriendlyNotice],
    ) -> list[FriendlyNotice]:
        """Convert background notices on the result into FriendlyNotices.

        The partition + map + deterministic-stitch flow can produce
        up to two kinds of notice in a single Background run:

        - ``background_split`` -- "We summarised in N parts."
        - ``background_record_split`` -- "One record was very long
          so we split it into pieces."

        Both come from the structured ``partition_report`` returned
        by ``call_background``. The wire payload carries the
        machine-readable codes alongside the plain-English text.
        """
        report = result.get("partition_report")
        out: list[FriendlyNotice] = []
        if report is not None:
            if getattr(report, "notice", None):
                out.append(background_split_notice(str(report.notice)))
            if getattr(report, "record_split_notice", None):
                out.append(
                    background_record_split_notice(str(report.record_split_notice))
                )
        for notice in out:
            notices.append(notice)
        return out

    @staticmethod
    def _record_background_part_errors(
        result: dict[str, Any],
        errors: list[str],
        errors_detail: list[FriendlyError],
    ) -> None:
        """Surface each failed Background part as its own structured error.

        The aggregated ``error`` field on the result already triggers
        ``_record_stage_error`` to add a single "background" entry,
        but the reviewer also needs to know WHICH parts failed so
        they can act ("part 3 of 5 failed -- pick fewer records, or
        re-run"). We label the per-part errors with a stage like
        ``background:part 3 of 5`` so the UI can group them under
        the Background section without polluting the simple
        per-stage error count.
        """
        parts = result.get("parts") or []
        for part in parts:
            code = part.get("error_code")
            if not code:
                continue
            index = int(part.get("index") or 0)
            total = int(part.get("total") or 0)
            message = str(part.get("error_message") or "")
            friendly = background_part_failed_error(index, total, message)
            errors.append(f"{friendly['stage']}:{message}")
            errors_detail.append(friendly)

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        # Lazy import keeps test imports cheap.
        from libs.neo4j_client.client import PatientGraphClient

        return PatientGraphClient()

    def _run_cypher(
        self, client: Any, query: str, **params: Any
    ) -> list[dict[str, Any]]:
        """Run Cypher via client.run() so transient connection errors retry."""
        from libs.referral_quality.inprocess_dry_run import is_write_cypher

        if self._dry_run and is_write_cypher(query):
            logger.info("dry_run=True - skipping SBAR write")
            return []
        if hasattr(client, "run"):
            return client.run(query, **params)
        with client.session() as session:
            return [dict(record) for record in session.run(query, **params)]

    def _emit(self, run_id: str, event_type: str, body: dict[str, Any]) -> None:
        try:
            payload = {"type": event_type, "run_id": run_id, **body}
            self._publish(run_id, payload)
        except Exception:
            logger.debug("publish_progress failed", exc_info=True)

    def _create_draft(
        self,
        client: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
        *,
        context_integrity_status: str = "passed",
        context_integrity_errors: str | None = None,
    ) -> None:
        self._run_cypher(
            client,
            CREATE_ASSESSMENT,
            patient_id=payload.situation.patient_id,
            assessment_id=assessment_id,
            run_id=payload.run_id,
            requested_by=payload.requested_by,
            tenant_id=payload.tenant_id,
            upstream_correlation_id=payload.upstream_correlation_id,
            source_system=payload.source_system,
            context_integrity_status=context_integrity_status,
            context_integrity_errors=context_integrity_errors,
            guideline_ids=payload.guideline_ids,
        )

    def _fail_context_integrity(
        self,
        *,
        client: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
        run_id: str,
        integrity: ContextIntegrityResult,
        started: float,
    ) -> SBARResult:
        """Stop the run when task record ids are not connected to the patient."""
        errors = [err.message for err in integrity.errors]
        errors_detail: list[FriendlyError] = [
            {
                "stage": "context",
                "code": err.code,
                "message": err.message,
            }
            for err in integrity.errors
        ]
        errors_json = json.dumps(
            [
                {
                    "code": err.code,
                    "message": err.message,
                    "record_type": err.record_type,
                    "record_id": err.record_id,
                }
                for err in integrity.errors
            ]
        )
        patient_missing = any(
            err.code == "patient_not_found" for err in integrity.errors
        )
        if not patient_missing:
            self._create_draft(
                client,
                payload,
                assessment_id,
                context_integrity_status="failed",
                context_integrity_errors=errors_json,
            )
            self._run_cypher(
                client,
                FINALISE_ASSESSMENT,
                assessment_id=assessment_id,
                content=(
                    "_SBAR generation stopped because the patient and record "
                    "ids in the task do not match._"
                ),
                status="error",
                context_integrity_status="failed",
                errors=errors,
                stt=None,
                stt_evidence=None,
                alternative_pathway=None,
                alternative_pathway_evidence=None,
                rtr=None,
                rtr_evidence=None,
                spoa_disposition=None,
                spoa_disposition_evidence=None,
            )
        duration = time.time() - started
        self._emit(
            run_id,
            "sbar_failed",
            {
                "assessment_id": assessment_id,
                "status": "error",
                "duration_s": round(duration, 3),
                "error_count": len(errors),
                "errors": list(errors_detail),
                "reason": "context_integrity",
            },
        )
        return SBARResult(
            assessment_id=assessment_id,
            status="error",
            situation="",
            background="",
            assessment="",
            recommendation="",
            content="",
            actions=[],
            rules=[],
            pathway_hints={},
            errors=errors,
            errors_detail=errors_detail,
            notices=[],
            duration_s=duration,
        )

    def _link_artefacts(
        self,
        client: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
    ) -> None:
        for ref in payload.situation.artifacts:
            try:
                if ref.type is SituationArtifactType.referral_request and ref.id:
                    self._run_cypher(
                        client,
                        LINK_ASSESSMENT_TO_REFERRAL_REQUEST,
                        assessment_id=assessment_id,
                        artifact_id=ref.id,
                    )
                elif ref.type is SituationArtifactType.procedure_request and ref.id:
                    self._run_cypher(
                        client,
                        LINK_ASSESSMENT_TO_PROCEDURE_REQUEST,
                        assessment_id=assessment_id,
                        artifact_id=ref.id,
                    )
            except Exception:
                logger.debug(
                    "link artefact failed for %s/%s",
                    ref.type.value,
                    ref.id,
                    exc_info=True,
                )
        if payload.encounter_id:
            try:
                self._run_cypher(
                    client,
                    LINK_ASSESSMENT_TO_ENCOUNTER,
                    assessment_id=assessment_id,
                    encounter_id=payload.encounter_id,
                )
            except Exception:
                logger.debug(
                    "link encounter %s failed", payload.encounter_id, exc_info=True
                )

    # -- Mandatory audit persistence (M2.8) -----------------------------

    def _persist_gate3_fields(
        self,
        client: Any,
        assessment_id: str,
        gate3: Any,
    ) -> None:
        try:
            persist_gate3_assessment_fields(
                client,
                assessment_id=assessment_id,
                gate3=gate3,
                run_cypher=self._run_cypher,
            )
        except Exception:
            logger.warning(
                "SBAR gate3: failed to persist referral reason / recall for %s",
                assessment_id,
                exc_info=True,
            )

    @staticmethod
    def _build_source_accounting(
        sources: list[Any],
        codes: list[Any],
    ) -> dict[str, int]:
        source_count = len(sources or [])
        code_count = len(codes or [])
        return {
            "source_count": source_count,
            "code_count": code_count,
            "total_sentences": max(code_count, source_count),
            "covered_sentences": code_count,
            "uncovered_sentences": max(source_count - code_count, 0),
        }

    def _persist_mandatory_audit(
        self,
        *,
        client: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
        run_id: str,
        bundle: AuditProvenanceBundle,
        recorder: LLMUsageRecorder,
        duration_s: float,
        stage_errors: list[str],
    ) -> None:
        """Persist manifest, provenance and audit link before completion."""
        audit_blockers = validate_completion_preconditions(bundle)
        if audit_blockers:
            raise AuditPersistenceError(", ".join(audit_blockers))

        manifest_json = json.dumps(
            bundle.execution_manifest, default=str, sort_keys=True
        )
        prompt_json = json.dumps(
            (bundle.execution_manifest or {}).get("prompts") or {},
            default=str,
            sort_keys=True,
        )
        model_json = json.dumps(
            bundle.model_provenance
            or (bundle.execution_manifest or {}).get("model")
            or {},
            default=str,
            sort_keys=True,
        )
        accounting_json = json.dumps(
            bundle.source_accounting, default=str, sort_keys=True
        )
        self._run_cypher(
            client,
            SET_ASSESSMENT_PROVENANCE,
            assessment_id=assessment_id,
            execution_manifest_json=manifest_json,
            prompt_provenance_json=prompt_json,
            model_provenance_json=model_json,
            source_accounting_json=accounting_json,
            audit_event_id=bundle.audit_event_id,
        )

        cfg = LLMCostConfig.from_env()
        first_error = stage_errors[0][:400] if stage_errors else None
        model_provider = "azure"
        model_tier = "small"
        if self._policy_runtime is not None:
            model_provider = self._policy_runtime.model_provider or model_provider
            model_tier = self._policy_runtime.model_tier or model_tier
        self._run_cypher(
            client,
            WRITE_SBAR_AUDIT_EVENT,
            id=bundle.audit_event_id,
            plan_definition_id="pd-referral-assessment",
            patient_id=payload.situation.patient_id,
            encounter_id=payload.encounter_id or "",
            run_id=run_id,
            event_type="sbar_requested",
            status="completed",
            step_count=int(recorder.usage.llm_calls),
            total_duration_ms=int(duration_s * 1000),
            entity_count=int(bundle.source_accounting.get("code_count") or 0),
            error_count=len(stage_errors),
            first_error=first_error,
            llm_input_tokens=int(recorder.usage.input_tokens),
            llm_output_tokens=int(recorder.usage.output_tokens),
            llm_cached_tokens=int(recorder.usage.cached_input_tokens),
            llm_cost_usd=round(recorder.cost_usd(cfg), 6),
            extraction_provider=model_provider,
            extraction_model_tier=model_tier,
            extraction_prompt_name="sbar",
            extraction_prompt_version=2,
            assessment_id=assessment_id,
        )

    # -- DI-LEO-AI-506 cost telemetry ----------------------------------

    def _record_usage_telemetry(
        self,
        *,
        client: Any,
        assessment_id: str,
        run_id: str,
        recorder: LLMUsageRecorder,
    ) -> None:
        """Best-effort LLM usage denormalisation for dashboard spend views."""
        try:
            cfg = LLMCostConfig.from_env()
        except Exception:
            logger.warning("LLMCostConfig.from_env failed", exc_info=True)
            cfg = None

        try:
            usage_dict = recorder.to_audit_dict(cfg)
            usage_dict["assessment_id"] = assessment_id
            usage_dict["run_id"] = run_id
            usage_dict["calls"] = [c.to_dict() for c in recorder.calls]
            cost_usd = float(usage_dict.get("cost_usd") or 0.0)
            self._run_cypher(
                client,
                SET_ASSESSMENT_USAGE,
                assessment_id=assessment_id,
                llm_usage_json=json.dumps(usage_dict, default=str),
                llm_input_tokens=int(usage_dict.get("input_tokens") or 0),
                llm_output_tokens=int(usage_dict.get("output_tokens") or 0),
                llm_cached_tokens=int(usage_dict.get("cached_input_tokens") or 0),
                llm_total_tokens=int(usage_dict.get("total_tokens") or 0),
                llm_calls=int(usage_dict.get("llm_calls") or 0),
                llm_cost_usd=round(cost_usd, 6),
                llm_latency_ms=int(usage_dict.get("total_latency_ms") or 0),
                llm_model_id=str(usage_dict.get("model_name") or ""),
                llm_model_provider=str(usage_dict.get("model_provider") or ""),
            )
        except Exception:
            logger.warning(
                "SBAR usage telemetry: failed to set Assessment.llm_usage_json"
                " for assessment %s",
                assessment_id,
                exc_info=True,
            )

    def _record_telemetry(
        self,
        *,
        client: Any,
        payload: SBARRequestPayload,
        assessment_id: str,
        run_id: str,
        status: str,
        errors: list[str],
        duration_s: float,
        recorder: LLMUsageRecorder,
    ) -> None:
        """Legacy wrapper retained for tests; delegates to split helpers."""
        manifest = (
            dict(self._policy_runtime.execution_manifest)
            if self._policy_runtime is not None
            else {}
        )
        bundle = AuditProvenanceBundle(
            execution_manifest=manifest,
            model_provenance=dict(manifest.get("model") or {}),
            source_accounting=self._build_source_accounting([], []),
            audit_event_id=f"audit-{run_id}",
        )
        try:
            self._persist_mandatory_audit(
                client=client,
                payload=payload,
                assessment_id=assessment_id,
                run_id=run_id,
                bundle=bundle,
                recorder=recorder,
                duration_s=duration_s,
                stage_errors=errors,
            )
        except AuditPersistenceError:
            logger.warning(
                "SBAR mandatory audit persistence failed for run %s",
                run_id,
                exc_info=True,
            )
        self._record_usage_telemetry(
            client=client,
            assessment_id=assessment_id,
            run_id=run_id,
            recorder=recorder,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _preview(text: str, max_chars: int = 240) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_chars else text[: max_chars - 1] + "..."


def _completeness_from_payload(payload: Any) -> dict[str, Any] | None:
    """Structured completeness from the referral pipeline, when present."""
    extra = getattr(payload, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    result = extra.get("completeness_result")
    return dict(result) if isinstance(result, dict) else None


def _first_specialty(resolved) -> str | None:
    for art in resolved.artifacts or []:
        if art.get("type") == SituationArtifactType.referral_request.value:
            spec = art.get("specialty") or ""
            if spec:
                return spec
    return None


def _assertion_value(raw: str | None) -> str:
    """Extract the scalar assertion string from a raw context value.

    The assertion field on a ResolvedCode can be either a plain string
    (e.g. "present") or a JSON-encoded context object
    (e.g. '{"assertion": "absent", "negated": true, ...}').
    Returns the assertion value in both cases, lower-cased.
    """
    if not raw:
        return "present"
    stripped = raw.strip()
    if stripped.startswith("{"):
        import json as _json

        try:
            obj = _json.loads(stripped)
            val = str(obj.get("assertion") or "present").strip().lower()
            if obj.get("negated"):
                return "absent"
            if obj.get("uncertain"):
                return "uncertain"
            return val
        except Exception:
            pass
    return stripped.lower()


def _assessment_demographics(patient_summary: dict[str, Any]) -> dict[str, Any]:
    """Return age/sex values suitable for deterministic guideline evaluation."""
    birth_date = patient_summary.get("birth_date") or patient_summary.get("birthDate")
    gender = patient_summary.get("gender") or patient_summary.get("sex")
    return {
        "patient_age": _age_years(birth_date),
        "patient_sex": _normalise_sex(gender),
    }


def _normalise_sex(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"female", "f", "woman"}:
        return "female"
    if text in {"male", "m", "man"}:
        return "male"
    return text or None


def _age_years(value: Any, *, today: date | None = None) -> float | None:
    if not value:
        return None
    if isinstance(value, datetime):
        birth = value.date()
    elif isinstance(value, date):
        birth = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            birth = datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                birth = date.fromisoformat(text[:10])
            except ValueError:
                return None
    today = today or datetime.now(timezone.utc).date()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return float(max(years, 0))


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
    policy_runtime = _policy_runtime_for_payload(payload)
    return await SBAROrchestrator(policy_runtime=policy_runtime).run(payload)


def _policy_runtime_for_payload(payload: SBARRequestPayload) -> Any | None:
    """Load pinned manifest for durable referral runs when available."""
    parent_run = str(payload.upstream_correlation_id or "").strip()
    if not parent_run:
        extra = dict(payload.extra or {})
        parent_run = str(extra.get("parent_run_id") or "").strip()
    if not parent_run:
        return None
    try:
        from libs.neo4j_client.client import PatientGraphClient
        from libs.sbar.policy_runtime import build_runtime, load_execution_manifest

        client = PatientGraphClient()
        try:
            manifest = load_execution_manifest(client, parent_run)
        finally:
            client.close()
        if manifest:
            return build_runtime(manifest)
    except Exception:
        logger.debug(
            "handle_sbar_message: execution manifest unavailable for %s",
            parent_run,
            exc_info=True,
        )
    return None


def _coerce_payload(body: dict[str, Any]) -> SBARRequestPayload:
    """Accept either {context: {...}} (workflow envelope) or a flat body."""
    candidate = body.get("context") if isinstance(body, dict) else None
    if isinstance(candidate, dict) and candidate.get("event_type") == "sbar_requested":
        return SBARRequestPayload.model_validate(candidate)
    if isinstance(body, dict) and body.get("event_type") == "sbar_requested":
        return SBARRequestPayload.model_validate(body)
    raise ValueError("body is not an sbar_requested payload")
