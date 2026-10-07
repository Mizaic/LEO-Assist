"""Shared pipeline state loader for durable pub/sub workflows.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Extracted from referral_durable_steps so both the legacy referral runner
and the new DurableStepRunner can share the same enrichment logic.
"""

from __future__ import annotations

import json
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
from libs.clinical_scoping.healthcare_service import (
    apply_healthcare_service_scope,
    resolve_healthcare_service,
)
from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_stage_store import PipelineStageStore
from libs.validation_lab.tenant import (
    VALIDATION_LAB_TENANT_ID,
    is_validation_lab_pipeline_state,
)

logger = logging.getLogger(__name__)

# Source node labels that already name the receiving-service anchor.
_HEALTHCARE_SCOPE_LABELS: frozenset[str] = frozenset(
    {"ReferralRequest", "CommunicationRequest"}
)

# Fallback anchors, tried in order, when the source label is rewritten.
_HEALTHCARE_SCOPE_STATE_KEYS: tuple[tuple[str, str], ...] = (
    ("ReferralRequest", "referral_id"),
    ("CommunicationRequest", "communication_request_id"),
)

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


def _resolve_tenant_id(
    state: dict[str, Any],
    request: StepRequest,
    body: dict[str, Any] | None,
) -> str:
    for candidate in (
        request.tenant_id,
        state.get("tenant_id"),
        (body or {}).get("tenant_id"),
        ((body or {}).get("context") or {}).get("tenant_id"),
    ):
        text = str(candidate or "").strip()
        if text:
            return text
    if is_validation_lab_pipeline_state(state) or is_validation_lab_pipeline_state(
        {"context": (body or {}).get("context") or {}}
    ):
        return VALIDATION_LAB_TENANT_ID
    return ""


def _merged_list(existing: Any, incoming: Any) -> list[Any]:
    """Append incoming items not already present, preserving order."""
    merged = list(existing or [])
    for item in incoming or []:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_loaded_state(state: dict[str, Any], loaded: dict[str, Any]) -> None:
    """Merge a loader's output into pipeline state, keeping warnings.

    A plain ``state.update`` replaces the warnings list, so a degradation
    another loader already recorded would vanish before anyone saw it.
    fail-closed-boundary.mdc rule 1 asks that a person can tell from the
    output that something happened, so warnings accumulate here.
    """
    warnings = _merged_list(state.get("warnings"), loaded.get("warnings"))
    state.update(loaded)
    if warnings:
        state["warnings"] = warnings


def load_document_chunks_into_state(
    client: PatientGraphClient,
    state: dict[str, Any],
    request: StepRequest,
) -> None:
    """Load referral chunks after the trigger chunk scope check.

    One pipeline: the Validation Lab and patient reprocess take the same
    path as a BAU production run, so a green Lab run is evidence about
    production. The Lab's synthetic graph satisfies the real scope query
    through its fixture data, not a code exemption -- scaffold_referral
    writes ReferralRequest -[:HAS_DOCUMENT]-> DocumentReference
    -[:HAS_CHUNK]-> Chunk plus ReferralRequest -[:FOR_PATIENT]-> Patient,
    and tags every chunk with the Lab tenant id.
    """
    chunk_ids = chunk_ids_from_state(state)
    if not chunk_ids or state.get("sentences"):
        return
    scope_errors = _validate_trigger_chunk_scope(client, state, chunk_ids)
    if scope_errors:
        state["errors"] = list(state.get("errors") or []) + scope_errors
        state["chunk_scope_failed"] = True
        return
    loaded = load_document_chunks_from_neo4j(
        client,
        chunk_ids,
        organization_id=str(
            state.get("healthcare_service_org_id") or state.get("org_id") or ""
        ),
    )
    _merge_loaded_state(state, loaded)
    if not loaded.get("errors"):
        return
    logger.warning(
        "document_chunks load failed run_id=%s chunk_count=%d errors=%s",
        request.run_id,
        len(chunk_ids),
        loaded.get("errors"),
    )
    state["errors"] = _merged_list(state.get("errors"), loaded.get("errors"))


def _validate_trigger_chunk_scope(
    client: PatientGraphClient,
    state: dict[str, Any],
    chunk_ids: list[str],
) -> list[str]:
    from libs.sbar.trigger_chunk_scope import (
        TriggerChunkScopeRequest,
        validate_trigger_chunk_scope,
    )

    tenant_id = str(state.get("tenant_id") or "")
    patient_id = str(state.get("patient_id") or "")
    referral_id = str(state.get("referral_id") or state.get("case_id") or "")
    document_reference_id = str(state.get("document_reference_id") or "")
    try:
        with client.session() as session:
            result = validate_trigger_chunk_scope(
                session,
                TriggerChunkScopeRequest(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    referral_id=referral_id or None,
                    document_reference_id=document_reference_id or None,
                    chunk_ids=chunk_ids,
                ),
            )
    except Exception:
        logger.warning("trigger chunk scope validation failed", exc_info=True)
        return ["trigger chunk scope validation failed"]
    if result.ok:
        state["chunk_ids"] = result.ordered_chunk_ids
        return []
    return [err.message for err in result.errors]


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
    _merge_loaded_state(state, loaded)
    if not loaded.get("errors"):
        return
    logger.warning(
        "communication_thread load failed run_id=%s cr_id=%s errors=%s",
        request.run_id,
        cr_id,
        loaded.get("errors"),
    )
    state["errors"] = _merged_list(state.get("errors"), loaded.get("errors"))


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
        "RETURN coalesce(toString(p.birthDate), '') AS birth_date, "
        "       coalesce(p.gender, '') AS gender, "
        "       coalesce(p.source, '') AS source",
        pid=patient_id,
    )
    if not rows:
        return
    row = rows[0]
    age = age_years_from_str(row.get("birth_date") or "")
    if age is None and str(row.get("source") or "") == "validation-lab":
        age = _validation_lab_age_fallback(client, patient_id)
    if age is not None:
        state["patient_age"] = age
    gender = str(row.get("gender") or "").strip().lower()
    if gender and not state.get("patient_sex"):
        state["patient_sex"] = (
            "female"
            if gender in {"female", "f", "woman"}
            else "male" if gender in {"male", "m", "man"} else gender or None
        )


def _validation_lab_age_fallback(
    client: PatientGraphClient,
    patient_id: str,
) -> float | None:
    """Derive age from ValidationCase prose when Patient.birthDate is missing."""
    from libs.validation_lab.patient_age import validation_lab_age_from_case_row

    rows = client.run(
        "MATCH (c:ValidationCase {patient_id: $pid}) "
        "RETURN c.id AS case_id, c.referral_text AS referral_text, "
        "       c.reason_for_submission AS reason_for_submission, "
        "       c.gp_encounter_json AS gp_encounter_json "
        "LIMIT 1",
        pid=patient_id,
    )
    if not rows:
        return None
    return validation_lab_age_from_case_row(dict(rows[0]))


def age_years_from_str(birth_date: Any) -> float | None:
    """Return decimal age from an ISO-8601 date string, or None."""
    from datetime import date as _date

    if birth_date is None:
        return None
    if hasattr(birth_date, "iso_format") and callable(birth_date.iso_format):
        val = str(birth_date.iso_format()).strip()[:10]
    elif hasattr(birth_date, "isoformat") and callable(birth_date.isoformat):
        try:
            val = str(birth_date.isoformat()).strip()[:10]
        except TypeError:
            val = str(birth_date or "").strip()[:10]
    else:
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
            "tenant_id": _resolve_tenant_id(state, request, body),
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
    enrich_patient_demographics(client, request.patient_id, state)
    enrich_patient_org_id(client, request.patient_id, state)
    _apply_healthcare_service_scope(client, state, request, source_type, source_id)
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
    _load_prompt_config(state, request.run_id)
    _load_execution_manifest(client, request.run_id, state)
    return state


def _healthcare_scope_source(
    state: dict[str, Any],
    source_type: str,
    source_id: str,
) -> tuple[str, str]:
    """Return the graph node label and id that carry receiving-service scope.

    ``default_source_fields`` rewrites ``source_node_type`` to "Chunk" for
    every referral bundle, and ``source_node_id`` to the DocumentReference
    id. Neither identifies the receiving trust, so the scope is resolved
    from the referral (or Advice and Guidance request) id on state instead.
    """
    if source_type in _HEALTHCARE_SCOPE_LABELS:
        return source_type, str(source_id or "").strip()
    for label, state_key in _HEALTHCARE_SCOPE_STATE_KEYS:
        candidate = str(state.get(state_key) or "").strip()
        if candidate:
            return label, candidate
    return "", ""


def _apply_healthcare_service_scope(
    client: PatientGraphClient,
    state: dict[str, Any],
    request: StepRequest,
    source_type: str,
    source_id: str,
) -> None:
    scope_type, scope_id = _healthcare_scope_source(state, source_type, source_id)
    if not scope_type:
        return
    service = resolve_healthcare_service(
        client,
        source_node_type=scope_type,
        source_node_id=scope_id,
    )
    apply_healthcare_service_scope(
        state,
        service,
        message_guideline_ids=list(request.guideline_ids or []),
    )


def _load_execution_manifest(
    client: PatientGraphClient,
    run_id: str,
    state: dict[str, Any],
) -> None:
    if not state.get("execution_manifest"):
        try:
            from libs.sbar.policy_runtime import load_execution_manifest

            manifest = load_execution_manifest(client, run_id)
            if manifest:
                state["execution_manifest"] = manifest
                state["execution_manifest_json"] = json.dumps(
                    manifest, sort_keys=True, default=str
                )
        except Exception:
            logger.debug(
                "execution_manifest unavailable for run %s",
                run_id,
                exc_info=True,
            )
    from libs.workflow.execution_manifest import apply_manifest_model_tier

    apply_manifest_model_tier(state)
