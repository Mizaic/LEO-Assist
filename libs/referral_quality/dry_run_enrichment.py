"""Read-only dry-run enrichment shared with the writeback path.

Applies the same Patient demographics and receiving-Service scope as
``load_step_state``. Cypher is MATCH-only. Does not start a run or write
facts.

Atlas trace:
  DO: DO-C4EAEB41
  DI: DI-D044C8F1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C4EAEB41")
"""

from __future__ import annotations

from typing import Any


def enrich_dry_run_state(client: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Populate completeness, guideline, and age/sex fields on dry-run state."""
    from libs.clinical_scoping.healthcare_service import (
        apply_healthcare_service_scope,
        resolve_healthcare_service,
    )
    from libs.workflow.step_state_loader import (
        _healthcare_scope_source,
        enrich_patient_demographics,
        enrich_patient_org_id,
    )

    patient_id = str(state.get("patient_id") or "")
    enrich_patient_demographics(client, patient_id, state)
    enrich_patient_org_id(client, patient_id, state)
    source_type, source_id = _healthcare_scope_source(
        state,
        str(state.get("source_node_type") or ""),
        str(state.get("source_node_id") or ""),
    )
    if not source_type:
        return state
    service = resolve_healthcare_service(
        client,
        source_node_type=source_type,
        source_node_id=source_id,
    )
    apply_healthcare_service_scope(
        state,
        service,
        message_guideline_ids=[
            str(item).strip()
            for item in list(state.get("guideline_ids") or [])
            if str(item).strip()
        ],
    )
    return state
