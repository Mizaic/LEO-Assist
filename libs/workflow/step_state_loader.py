"""Shared pipeline state loader for durable pub/sub workflows.

Extracted from referral_durable_steps so both the legacy referral runner
and the new DurableStepRunner can share the same enrichment logic.
"""

from __future__ import annotations

import logging
from typing import Any

from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.document_chunk_loader import (
    chunk_ids_from_state,
    is_document_chunks_mode,
    load_document_chunks_from_neo4j,
    merge_referral_message_fields,
)
from libs.pipeline.communication_thread_loader import (
    is_communication_thread_mode,
    load_communication_thread_from_neo4j,
)
from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_stage_store import PipelineStageStore

logger = logging.getLogger(__name__)

REFERRAL_HANDOFF_KEYS: tuple[str, ...] = (
    "chunk_ids",
    "communication_request_id",
    "document_reference_id",
    "text_segmentation_mode",
    "referral_id",
    "ubrn",
    "guideline_ids",
    "org_id",
)


def referral_handoff_values(
    body: dict[str, Any] | None,
    request: StepRequest,
) -> dict[str, Any]:
    """Collect handoff fields from message top-level, nested context, and request."""
    raw_body = body or {}
    body_context = dict(raw_body.get("context") or {})
    request_context = dict(request.context or {})
    handoff: dict[str, Any] = {}
    for key in REFERRAL_HANDOFF_KEYS:
        for value in (
            raw_body.get(key),
            body_context.get(key),
            request_context.get(key),
        ):
            if value is not None:
                handoff[key] = value
                break
    return handoff


def apply_referral_handoff_fields(
    state: dict[str, Any],
    request: StepRequest,
    body: dict[str, Any] | None,
) -> None:
    """Promote HCCP referral handoff fields onto top-level pipeline state."""
    handoff = referral_handoff_values(body, request)
    state.update(handoff)
    nested_context = dict((body or {}).get("context") or {})
    nested_context.update(request.context or {})
    nested_context.update(handoff)
    state.update(
        merge_referral_message_fields({**(body or {}), "context": nested_context})
    )


def default_source_fields(
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
    if is_communication_thread_mode(state):
        cr_id = str(state.get("communication_request_id") or "").strip()
        return (
            "CommunicationRequest",
            cr_id or (request.source_node_id or request.encounter_id),
            "note",
        )
    return (
        request.source_node_type or "Encounter",
        request.source_node_id or request.encounter_id,
        text_property,
    )


def load_document_chunks_into_state(
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


def load_communication_thread_into_state(
    client: PatientGraphClient,
    state: dict[str, Any],
    request: StepRequest,
) -> None:
    if state.get("sentences"):
        return
    cr_id = str(state.get("communication_request_id") or "").strip()
    if not cr_id:
        state["errors"] = list(state.get("errors") or []) + [
            "communication_thread mode requires communication_request_id"
        ]
        return
    loaded = load_communication_thread_from_neo4j(
        client,
        cr_id,
        chunk_ids=chunk_ids_from_state(state) or None,
    )
    state.update(loaded)
    if not loaded.get("errors"):
        return
    logger.warning(
        "communication_thread load failed run_id=%s cr_id=%s errors=%s",
        request.run_id,
        cr_id,
        loaded.get("errors"),
    )
    state["errors"] = list(state.get("errors") or []) + list(loaded.get("errors") or [])


def enrich_patient_org_id(
    client: PatientGraphClient,
    patient_id: str,
    state: dict[str, Any],
) -> None:
    """Set state.org_id from job context or patient registration.

    Prefer an existing org_id (e.g. context override). Otherwise derive from
    HAS_GENERAL_PRACTITIONER or REGISTERED_IN. Missing org is allowed --
    never raises.
    """
    existing = str(state.get("org_id") or "").strip()
    if existing:
        state["org_id"] = existing
        return
    if not patient_id:
        return
    try:
        rows = client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid "
            "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "OPTIONAL MATCH (p)-[:REGISTERED_IN]->(reg) "
            "RETURN coalesce(gp.id, reg.id) AS org_id "
            "LIMIT 1",
            pid=patient_id,
        )
    except Exception:
        logger.debug("enrich_patient_org_id query failed", exc_info=True)
        return
    if not rows:
        return
    org_id = rows[0].get("org_id")
    if org_id:
        state["org_id"] = str(org_id)


def enrich_patient_demographics(
    client: PatientGraphClient,
    patient_id: str,
    state: dict[str, Any],
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
    age = age_years_from_str(row.get("birth_date") or "")
    if age is not None:
        state["patient_age"] = age
    gender = str(row.get("gender") or "").strip().lower()
    if gender and not state.get("patient_sex"):
        state["patient_sex"] = (
            "female"
            if gender in {"female", "f", "woman"}
            else "male" if gender in {"male", "m", "man"} else gender or None
        )


def age_years_from_str(birth_date: str) -> float | None:
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


def _load_prompt_config(state: dict[str, Any], run_id: str) -> None:
    """Load extraction prompt config if absent, matching WorkflowEngine behaviour."""
    if "prompt_config" in state:
        return
    try:
        from libs.prompts.registry import get_prompt_config

        state["prompt_config"] = get_prompt_config("extraction", version=1)
    except Exception:
        logger.debug(
            "prompt_config unavailable for run %s; extraction will use defaults",
            run_id,
        )


def load_step_state(
    client: PatientGraphClient,
    store: PipelineStageStore,
    request: StepRequest,
    *,
    extra_state: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and enrich pipeline state for a durable step.

    Pulls accumulated outputs from the store, merges handoff fields from the
    incoming message, enriches demographics, and loads document chunks or
    encounter text as appropriate.
    """
    state = store.load_accumulated_state(request.run_id)
    apply_referral_handoff_fields(state, request, body)
    if extra_state:
        state.update(extra_state)
    source_type, source_id, source_text_property = default_source_fields(request, state)
    state.update(
        {
            "patient_id": request.patient_id,
            "encounter_id": request.encounter_id,
            "run_id": request.run_id,
            "plan_definition_id": request.plan_definition_id,
            "workflow_id": request.workflow_id,
            "tenant_id": request.tenant_id,
            "requested_by": request.requested_by,
            "source_node_type": source_type,
            "source_node_id": source_id,
            "source_text_property": source_text_property,
            "guideline_scope_type": "guideline" if request.guideline_ids else "global",
            "guideline_scope_id": (
                request.guideline_ids[0] if request.guideline_ids else None
            ),
            "guideline_id": (
                request.guideline_ids[0] if request.guideline_ids else None
            ),
            "completeness_domain": request.completeness_domain,
            "completeness_subdomain": request.completeness_subdomain,
            "guideline_ruleset_version": request.guideline_ruleset_version,
            "errors": list(state.get("errors") or []),
        }
    )
    if is_document_chunks_mode(state):
        load_document_chunks_into_state(client, state, request)
    elif is_communication_thread_mode(state):
        load_communication_thread_into_state(client, state, request)
    elif not state.get("encounter_text") and request.encounter_id:
        rows = client.run(
            "MATCH (e:Encounter {id: $encounter_id}) "
            "RETURN coalesce(e.text, '') AS text",
            encounter_id=request.encounter_id,
        )
        if rows:
            state["encounter_text"] = rows[0].get("text") or ""
    enrich_patient_demographics(client, request.patient_id, state)
    enrich_patient_org_id(client, request.patient_id, state)
    _load_prompt_config(state, request.run_id)
    return state
