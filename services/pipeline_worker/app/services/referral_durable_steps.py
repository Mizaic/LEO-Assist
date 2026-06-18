"""Durable pub/sub steps for referral assessment workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from libs.cypher.pipeline_stage_queries import WRITE_PIPELINE_RUN_COMPLETION
from libs.cypher.sbar_assessment_queries import SET_ASSESSMENT_COMPLETENESS
from libs.message_bus.base import Message, MessageBusAdapter
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline_graph.registry import get_registry
from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
    SummarisationContext,
)
from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    is_document_chunks_mode,
    load_document_chunks_from_neo4j,
    chunk_ids_from_state,
    merge_referral_message_fields,
)
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_stage_store import PipelineStageStore

logger = logging.getLogger(__name__)

PIPELINE_QUEUE = "pipeline-jobs"
REFERRAL_OUTPUT_QUEUE = "referral-assessments-output"
REFERRAL_WORKFLOW_ID = "pd-referral-assessment"


@dataclass(frozen=True)
class ReferralStepDefinition:
    event_type: str
    step_id: str
    subgraph_id: str | None
    next_event_type: str | None
    next_step_id: str | None
    # When set, published to REFERRAL_OUTPUT_QUEUE after the step
    # completes. Used for terminal steps that must signal downstream
    # consumers. next_event_type / next_step_id should both be None
    # for these steps so the PipelineRun is marked "completed".
    completion_event_type: str | None = None
    extra_state: dict[str, Any] = field(default_factory=dict)
    loads: tuple[str, ...] = ()
    persists: tuple[str, ...] = ()


REFERRAL_STEPS: tuple[ReferralStepDefinition, ...] = (
    ReferralStepDefinition(
        "extraction_requested",
        "durable-ref-extraction",
        "extraction",
        "post_processing_requested",
        "durable-ref-post-processing",
        loads=("Encounter.text", "Chunk.text"),
        persists=("ExtractionResult",),
    ),
    ReferralStepDefinition(
        "post_processing_requested",
        "durable-ref-post-processing",
        "post_processing",
        "relation_linking_requested",
        "durable-ref-relation-linking",
        loads=("ExtractionResult",),
        persists=("PostProcessingResult",),
    ),
    ReferralStepDefinition(
        "relation_linking_requested",
        "durable-ref-relation-linking",
        "relation_linking",
        "extraction_check_requested",
        "durable-ref-extraction-check",
        loads=("PostProcessingResult",),
        persists=("RelationLinkingResult",),
    ),
    ReferralStepDefinition(
        "extraction_check_requested",
        "durable-ref-extraction-check",
        "extraction_check",
        "terminology_requested",
        "durable-ref-terminology",
        loads=("RelationLinkingResult",),
        persists=("ExtractionCheckResult",),
    ),
    ReferralStepDefinition(
        "terminology_requested",
        "durable-ref-terminology",
        "terminology",
        "clinical_facts_persist_requested",
        "durable-ref-clinical-facts-persist",
        loads=("ExtractionCheckResult",),
        persists=("TerminologyResult",),
    ),
    ReferralStepDefinition(
        "clinical_facts_persist_requested",
        "durable-ref-clinical-facts-persist",
        "persist",
        "compliance_requested",
        "durable-ref-compliance",
        extra_state={"output_target": "patient_graph"},
        loads=("TerminologyResult",),
        persists=("DOCUMENTS", "CodingDecision"),
    ),
    ReferralStepDefinition(
        "compliance_requested",
        "durable-ref-compliance",
        "compliance",
        "completeness_requested",
        "durable-ref-completeness",
        loads=("DOCUMENTS", "TerminologyResult"),
        persists=("GuidelineResult",),
    ),
    ReferralStepDefinition(
        "completeness_requested",
        "durable-ref-completeness",
        "quality_check",
        "sbar_requested",
        "durable-ref-sbar",
        loads=("DOCUMENTS", "GuidelineResult"),
        persists=("CompletenessResult", "QualityReport"),
    ),
    ReferralStepDefinition(
        "sbar_requested",
        "durable-ref-sbar",
        None,
        None,
        None,
        completion_event_type="referral_assessment_completed",
        loads=("DOCUMENTS", "GuidelineResult", "CompletenessResult"),
        persists=("Assessment",),
    ),
)

REFERRAL_STEP_BY_EVENT = {step.event_type: step for step in REFERRAL_STEPS}


def is_referral_durable_message(body: dict[str, Any]) -> bool:
    event_type = str(body.get("event_type") or "")
    workflow_id = str(body.get("workflow_id") or body.get("plan_definition_id") or "")
    return event_type in REFERRAL_STEP_BY_EVENT and workflow_id == REFERRAL_WORKFLOW_ID


def is_referral_durable_start(body: dict[str, Any]) -> bool:
    return (
        str(body.get("event_type") or "") == "referral-received"
        and str(body.get("plan_definition_id") or "") == REFERRAL_WORKFLOW_ID
    )


async def start_referral_durable_workflow(
    body: dict[str, Any],
    *,
    bus: MessageBusAdapter,
    queue_name: str = PIPELINE_QUEUE,
) -> None:
    first = REFERRAL_STEPS[0]
    request = StepRequest.from_message(
        {
            **body,
            "event_type": first.event_type,
            "workflow_id": REFERRAL_WORKFLOW_ID,
            "step_id": first.step_id,
            "context": merge_referral_message_fields(body),
        }
    )
    client = PatientGraphClient()
    try:
        store = PipelineStageStore(client)
        store.ensure_schema()
        store.upsert_run(request, status="running")
    finally:
        client.close()
    await _publish_next(bus, queue_name, request, first.event_type, first.step_id)


async def handle_referral_durable_message(
    body: dict[str, Any],
    *,
    bus: MessageBusAdapter | None,
    publish_progress: Any | None = None,
    queue_name: str = PIPELINE_QUEUE,
) -> StepResult:
    request = StepRequest.from_message(body)
    definition = REFERRAL_STEP_BY_EVENT[request.event_type]
    if not request.step_id:
        request = StepRequest.from_message({**body, "step_id": definition.step_id})
    started = time.monotonic()
    client = PatientGraphClient()
    try:
        store = PipelineStageStore(client)
        store.ensure_schema()
        store.upsert_run(request, status="running")
        loaded = _load_step_state(client, store, request, definition, body=body)
        store.start_stage(request, loaded)
        _emit(publish_progress, request, "durable_step_started", definition)
        result = await _run_definition(request, definition, loaded)
        result = _with_metrics(result, started, loaded)
        store.complete_stage(request, result)
        _emit(publish_progress, request, "durable_step_completed", definition, result)
        if bus and result.next_event_type and result.next_step_id:
            await _publish_next(
                bus,
                queue_name,
                request,
                result.next_event_type,
                result.next_step_id,
            )
        elif bus and definition.completion_event_type:
            await _publish_completion(bus, request, result, definition)
        return result
    except Exception as exc:
        logger.exception("Durable referral step failed")
        result = StepResult(status="failed", errors=[str(exc)])
        try:
            store.complete_stage(request, result)
        except Exception:
            logger.debug("Failed to persist durable step failure", exc_info=True)
        _emit(publish_progress, request, "durable_step_failed", definition, result)
        raise
    finally:
        client.close()


_REFERRAL_HANDOFF_KEYS = (
    "chunk_ids",
    "document_reference_id",
    "text_segmentation_mode",
    "referral_id",
    "ubrn",
)


def _referral_handoff_values(
    body: dict[str, Any] | None,
    request: StepRequest,
) -> dict[str, Any]:
    """Collect handoff fields from message top-level, nested context, and request."""
    raw_body = body or {}
    body_context = dict(raw_body.get("context") or {})
    request_context = dict(request.context or {})
    handoff: dict[str, Any] = {}
    for key in _REFERRAL_HANDOFF_KEYS:
        for value in (
            raw_body.get(key),
            body_context.get(key),
            request_context.get(key),
        ):
            if value is not None:
                handoff[key] = value
                break
    return handoff


def _apply_referral_handoff_fields(
    state: dict[str, Any],
    request: StepRequest,
    body: dict[str, Any] | None,
) -> None:
    """Promote HCCP referral handoff fields onto top-level pipeline state."""
    handoff = _referral_handoff_values(body, request)
    state.update(handoff)
    nested_context = dict((body or {}).get("context") or {})
    nested_context.update(request.context or {})
    nested_context.update(handoff)
    state.update(merge_referral_message_fields({**(body or {}), "context": nested_context}))


def _default_source_fields(
    request: StepRequest,
    state: dict[str, Any],
) -> tuple[str, str, str]:
    text_property = request.source_text_property or "text"
    if is_document_chunks_mode(state):
        doc_ref = str(state.get("document_reference_id") or "").strip()
        return (
            "Chunk",
            doc_ref or (request.source_node_id or request.encounter_id),
            text_property,
        )
    return (
        request.source_node_type or "Encounter",
        request.source_node_id or request.encounter_id,
        text_property,
    )


def _load_document_chunks_into_state(
    client: PatientGraphClient,
    state: dict[str, Any],
    request: StepRequest,
) -> None:
    chunk_ids = chunk_ids_from_state(state)
    if not chunk_ids or state.get("sentences"):
        return
    loaded = load_document_chunks_from_neo4j(client, chunk_ids)
    state.update(loaded)
    if not loaded.get("errors"):
        return
    logger.warning(
        "document_chunks load failed run_id=%s chunk_count=%d errors=%s",
        request.run_id,
        len(chunk_ids),
        loaded.get("errors"),
    )
    state["errors"] = list(state.get("errors") or []) + list(loaded.get("errors") or [])


def _load_step_state(
    client: PatientGraphClient,
    store: PipelineStageStore,
    request: StepRequest,
    definition: ReferralStepDefinition,
    *,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = store.load_accumulated_state(request.run_id)
    _apply_referral_handoff_fields(state, request, body)
    state.update(definition.extra_state)
    source_type, source_id, source_text_property = _default_source_fields(
        request, state
    )
    state.update(
        {
            "patient_id": request.patient_id,
            "encounter_id": request.encounter_id,
            "run_id": request.run_id,
            "plan_definition_id": request.plan_definition_id,
            "source_node_type": source_type,
            "source_node_id": source_id,
            "source_text_property": source_text_property,
            "guideline_scope_type": "guideline",
            "guideline_scope_id": request.guideline_id,
            "guideline_id": request.guideline_id,
            "completeness_domain": request.completeness_domain,
            "completeness_subdomain": request.completeness_subdomain,
            "errors": list(state.get("errors") or []),
        }
    )
    if is_document_chunks_mode(state):
        _load_document_chunks_into_state(client, state, request)
    elif not state.get("encounter_text") and request.encounter_id:
        rows = client.run(
            "MATCH (e:Encounter {id: $encounter_id}) "
            "RETURN coalesce(e.text, '') AS text",
            encounter_id=request.encounter_id,
        )
        if rows:
            state["encounter_text"] = rows[0].get("text") or ""
    _enrich_patient_demographics(client, request.patient_id, state)
    return state


def _enrich_patient_demographics(
    client: PatientGraphClient,
    patient_id: str,
    state: dict,
) -> None:
    """Populate patient_age and patient_sex in state from the Patient node.

    Age-gated guideline rules fail CLOSED when patient_age is absent.
    Querying the Patient node here ensures every subgraph (compliance,
    terminology, SBAR) gets the demographics without each one re-querying.
    """
    if state.get("patient_age") is not None:
        return
    if not patient_id:
        return
    rows = client.run(
        "MATCH (p:Patient {id: $pid}) "
        "RETURN coalesce(p.birthDate, '') AS birth_date, "
        "       coalesce(p.gender, '')    AS gender",
        pid=patient_id,
    )
    if not rows:
        return
    row = rows[0]
    age = _age_years_from_str(row.get("birth_date") or "")
    if age is not None:
        state["patient_age"] = age
    gender = str(row.get("gender") or "").strip().lower()
    if gender and not state.get("patient_sex"):
        state["patient_sex"] = (
            "female"
            if gender in {"female", "f", "woman"}
            else "male" if gender in {"male", "m", "man"} else gender or None
        )


def _age_years_from_str(birth_date: str) -> float | None:
    """Return decimal age from an ISO-8601 date string, or None."""
    from datetime import date as _date

    val = str(birth_date or "").strip()[:10]
    if not val:
        return None
    try:
        parts = val.split("-")
        birth = _date(int(parts[0]), int(parts[1]), int(parts[2]))
        today = _date.today()
        years = today.year - birth.year
        if (today.month, today.day) < (birth.month, birth.day):
            years -= 1
        return float(years)
    except (ValueError, IndexError):
        return None


def _persist_completeness_to_assessment(
    assessment_id: str,
    completeness_result: dict[str, Any],
) -> None:
    """Write completeness_result JSON to the :Assessment node.

    Called after the SBAR step so the SDK endpoint can return it
    to the widget, which renders the completeness panel.
    """
    client = PatientGraphClient()
    try:
        client.run(
            SET_ASSESSMENT_COMPLETENESS,
            assessment_id=assessment_id,
            completeness_result_json=json.dumps(completeness_result),
        )
    except Exception as exc:
        logger.warning(
            "Could not persist completeness result for assessment %s: %s",
            assessment_id,
            exc,
        )
    finally:
        client.close()


async def _run_definition(
    request: StepRequest,
    definition: ReferralStepDefinition,
    loaded: dict[str, Any],
) -> StepResult:
    if definition.event_type == "sbar_requested":
        output = await _run_sbar_orchestrator(request)
        completeness_result = loaded.get("completeness_result")
        if completeness_result:
            assessment_id = _assessment_id(request.run_id, request.encounter_id)
            _persist_completeness_to_assessment(assessment_id, completeness_result)
    elif definition.subgraph_id:
        graph = get_registry().build(definition.subgraph_id)
        output = await asyncio.to_thread(graph.invoke, loaded)
    else:
        output = {}
    return StepResult(
        status="completed",
        output=dict(output or {}),
        errors=list((output or {}).get("errors") or []),
        next_event_type=definition.next_event_type,
        next_step_id=definition.next_step_id,
    )


async def _run_sbar_orchestrator(request: StepRequest) -> dict[str, Any]:
    from services.pipeline_worker.app.services.sbar_orchestrator import (
        SBAROrchestrator,
    )

    assessment_id = _assessment_id(request.run_id, request.encounter_id)
    artifacts = [
        SBARArtifactRef(
            type=SituationArtifactType.encounter,
            id=request.encounter_id,
        ),
        SBARArtifactRef(
            type=SituationArtifactType.summarisation_context,
            context_value=SummarisationContext.two_week_wait,
        ),
    ]
    referral_id = str(request.context.get("referral_id") or "").strip()
    if referral_id:
        artifacts.append(
            SBARArtifactRef(
                type=SituationArtifactType.referral_request,
                id=referral_id,
            )
        )
    background = [
        SBARBackgroundSourceRef(
            type=BackgroundSourceType.encounter,
            id=request.encounter_id,
        )
    ]
    document_reference_id = str(
        request.context.get("document_reference_id") or ""
    ).strip()
    if document_reference_id:
        background.append(
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.document_reference,
                id=document_reference_id,
            )
        )
    payload = SBARRequestPayload(
        run_id=f"{request.run_id}:sbar",
        requested_by=request.requested_by,
        tenant_id=request.tenant_id,
        assessment_id=assessment_id,
        encounter_id=request.encounter_id,
        concern="Referral assessment SBAR for clinician review.",
        guideline_ids=[request.guideline_id] if request.guideline_id else [],
        situation=SBARSituationInput(
            patient_id=request.patient_id,
            artifacts=artifacts,
        ),
        background=background,
        upstream_correlation_id=request.run_id,
        source_system="referral-assessment-pipeline",
        extra={"parent_run_id": request.run_id, "workflow_id": request.workflow_id},
    )
    result = await SBAROrchestrator().run(payload)
    return {
        "sbar_assessment_id": result.assessment_id,
        "sbar_status": result.status,
        "sbar_sections": {
            "situation": result.situation,
            "background": result.background,
            "assessment": result.assessment,
            "recommendation": result.recommendation,
        },
        "sbar_report": {
            "situation": result.situation,
            "background": result.background,
            "assessment": result.assessment,
            "recommendation": result.recommendation,
            "assessment_id": result.assessment_id,
            "actions": result.actions,
            "rules": result.rules,
        },
        "errors": result.errors,
        "review_status": "pending_review",
    }


def _assessment_id(run_id: str, encounter_id: str) -> str:
    raw = f"{run_id}:{encounter_id}:sbar".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _with_metrics(
    result: StepResult, started: float, loaded: dict[str, Any]
) -> StepResult:
    metrics = dict(result.metrics)
    metrics.update(
        {
            "duration_ms": int((time.monotonic() - started) * 1000),
            "entity_count": len(
                loaded.get("entities") or result.output.get("entities") or []
            ),
        }
    )
    return StepResult(
        status=result.status,
        output=result.output,
        output_refs=result.output_refs,
        warnings=result.warnings,
        errors=result.errors,
        metrics=metrics,
        next_event_type=result.next_event_type,
        next_step_id=result.next_step_id,
    )


async def _publish_next(
    bus: MessageBusAdapter,
    queue_name: str,
    request: StepRequest,
    event_type: str,
    step_id: str,
) -> None:
    await bus.send(
        queue_name,
        Message(
            body=request.to_message(event_type, step_id),
            correlation_id=request.run_id,
            subject=event_type.replace("_", "-"),
        ),
    )


async def _publish_completion(
    bus: MessageBusAdapter,
    request: StepRequest,
    result: StepResult,
    definition: ReferralStepDefinition,
) -> None:
    body = _build_completion_body(request, result, definition)
    await bus.send(
        REFERRAL_OUTPUT_QUEUE,
        Message(
            body=body,
            correlation_id=request.run_id,
            subject="referral-assessment-completed",
        ),
    )
    _persist_completion_event(request.run_id, body)


def _build_completion_body(
    request: StepRequest,
    result: StepResult,
    definition: ReferralStepDefinition,
) -> dict[str, Any]:
    status = "completed_with_errors" if result.errors else "completed"
    return {
        "event_type": definition.completion_event_type,
        "run_id": request.run_id,
        "workflow_id": request.workflow_id,
        "plan_definition_id": request.plan_definition_id,
        "patient_id": request.patient_id,
        "encounter_id": request.encounter_id,
        "assessment_id": result.output.get("sbar_assessment_id"),
        "guideline_id": request.guideline_id,
        "completeness_domain": request.completeness_domain,
        "completeness_subdomain": request.completeness_subdomain,
        "status": status,
        "errors": list(result.errors),
        "context": dict(request.context),
    }


def _persist_completion_event(run_id: str, body: dict[str, Any]) -> None:
    """Write the completion event payload to the PipelineRun node.

    Best-effort: failures are logged at WARNING and never block the
    publish. This gives the scenario panel an audit trail of exactly
    what was dispatched to the output queue.
    """
    try:
        client = PatientGraphClient()
        try:
            client.run(
                WRITE_PIPELINE_RUN_COMPLETION,
                run_id=run_id,
                completion_event_json=json.dumps(body, default=str),
            )
        finally:
            client.close()
    except Exception:
        logger.warning(
            "Failed to persist completion event for run %s", run_id, exc_info=True
        )


def _emit(
    publisher: Any | None,
    request: StepRequest,
    event_type: str,
    definition: ReferralStepDefinition,
    result: StepResult | None = None,
) -> None:
    if not publisher:
        return
    payload = {
        "type": event_type,
        "run_id": request.run_id,
        "patient_id": request.patient_id,
        "encounter_id": request.encounter_id,
        "workflow_id": request.workflow_id,
        "step_id": definition.step_id,
        "step_event_type": definition.event_type,
        "status": result.status if result else "running",
    }
    if result:
        payload["errors"] = result.errors
        payload["metrics"] = result.metrics
    publisher(request.run_id, payload)
