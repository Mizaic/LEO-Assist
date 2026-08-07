"""Validation Lab A&G pipeline helpers (resolve ubrn + enqueue).

Atlas trace:
  DO: DO-E981C7B1
  DI: DI-D6E5F94E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E981C7B1")
"""

from __future__ import annotations

from typing import Any

from libs.cypher.communication_thread_queries import (
    RESOLVE_COMMUNICATION_REQUEST_BY_UBRN,
)
from libs.referral_simulator.message import build_communication_assessment_message
from libs.validation_lab.tenant import VALIDATION_LAB_TENANT_ID


class AgPipelineError(ValueError):
    """Invalid A&G pipeline input or missing graph data."""


def resolve_communication_request(client: Any, ubrn: str) -> dict[str, str]:
    """Resolve CommunicationRequest + patient from an existing ubrn."""
    ubrn_val = str(ubrn or "").strip()
    if not ubrn_val:
        raise AgPipelineError("ubrn is required")
    rows = client.run(RESOLVE_COMMUNICATION_REQUEST_BY_UBRN, ubrn=ubrn_val)
    if not rows:
        raise AgPipelineError(f"CommunicationRequest not found for ubrn={ubrn_val}")
    row = rows[0]
    cr_id = str(row.get("communication_request_id") or "").strip()
    patient_id = str(row.get("patient_id") or "").strip()
    resolved_ubrn = str(row.get("ubrn") or ubrn_val).strip()
    if not cr_id or not patient_id:
        raise AgPipelineError(f"Incomplete CommunicationRequest for ubrn={ubrn_val}")
    return {
        "patient_id": patient_id,
        "communication_request_id": cr_id,
        "ubrn": resolved_ubrn,
        "encounter_id": f"{resolved_ubrn}:ag-assessment",
    }


def build_ag_pipeline_message(
    *,
    patient_id: str,
    communication_request_id: str,
    ubrn: str,
    run_id: str,
    plan_definition_id: str = "pd-referral-assessment",
    guideline_id: str | None = None,
    completeness_domain: str | None = None,
    completeness_subdomain: str | None = None,
    guideline_ruleset_version: str | None = None,
    chunk_ids: list[str] | None = None,
    context: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Wrap the communication_thread bus message with Lab run metadata."""
    body = build_communication_assessment_message(
        patient_id=patient_id,
        communication_request_id=communication_request_id,
        ubrn=ubrn,
        run_id=run_id,
        plan_definition_id=plan_definition_id,
        guideline_id=guideline_id,
        completeness_domain=completeness_domain,
        completeness_subdomain=completeness_subdomain,
        guideline_ruleset_version=guideline_ruleset_version,
        chunk_ids=chunk_ids,
        context=context,
    )
    body["dry_run"] = dry_run
    body["capture_validation_output"] = True
    body["tenant_id"] = VALIDATION_LAB_TENANT_ID
    return body
