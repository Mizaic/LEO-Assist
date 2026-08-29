"""SBAR assessment subgraph.

Atlas trace:
  UN: UN-AF530E8E
  DI: DI-E0ACC8C4
  DO: DO-D2055499
  VT: VT-2B0651CD

Wraps SBAROrchestrator.run() as a LangGraph subgraph so it can be driven
by both the legacy referral durable steps runner and the new
DurableStepRunner.

The orchestrator performs four internal stages (Situation, Background,
Assessment, Recommendation) with incremental Neo4j writes. The wrapper
keeps these opaque: it calls orchestrator.run() as a single unit.

Runs in a thread via asyncio.to_thread(subgraph.invoke, state), so
async calls use asyncio.run() which is safe from a worker thread.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class SBARSubgraphState(TypedDict, total=False):
    patient_id: str
    encounter_id: str
    run_id: str
    workflow_id: str
    plan_definition_id: str
    tenant_id: str
    requested_by: str
    guideline_ids: list[str]
    referral_id: str
    document_reference_id: str
    referral_reason: str
    source_node_type: str
    compliance_result: dict[str, Any]
    healthcare_service_id: str
    healthcare_service_name: str
    healthcare_service_specialty: str
    healthcare_service_spoa_id: str
    healthcare_service_missing: bool
    form_schema_fingerprint: str
    form_clinical_section: str
    form_sections: list[dict[str, Any]]
    completeness_result: dict[str, Any]
    dry_run: bool
    sbar_assessment_id: str
    sbar_status: str
    sbar_sections: dict[str, Any]
    sbar_report: dict[str, Any]
    review_status: str
    errors: list[str]
    warnings: list[str]


def _partition_pipeline_messages(
    messages: list[str],
) -> tuple[list[str], list[str]]:
    """Keep audit blockers as errors so a failed check cannot look clean."""
    errors: list[str] = []
    warnings: list[str] = []
    for raw in messages:
        msg = str(raw or "").strip()
        if not msg:
            continue
        errors.append(msg)
    return errors, warnings


def _form_sections_from_state(state: SBARSubgraphState) -> list[dict[str, Any]]:
    existing = list(state.get("form_sections") or [])
    if existing:
        return existing
    fingerprint = str(state.get("form_schema_fingerprint") or "").strip()
    if not fingerprint:
        return []
    from libs.pipeline.form_schema_store import get_cached_schema

    schema = get_cached_schema(fingerprint)
    if schema is None:
        return []
    return [
        {
            "section_id": section.section_id,
            "section_type": section.section_type,
            "label": section.label,
            "start_pattern": section.start_pattern,
        }
        for section in schema.sections
    ]


def _assessment_id(run_id: str, encounter_id: str) -> str:
    raw = f"{run_id}:{encounter_id}:sbar".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _run_sbar(state: SBARSubgraphState) -> dict[str, Any]:
    try:
        return asyncio.run(_async_run_sbar(state))
    except Exception as exc:
        logger.exception("SBAR orchestrator failed")
        return {"sbar_status": "error", "errors": [str(exc)]}


async def _async_run_sbar(state: SBARSubgraphState) -> dict[str, Any]:
    from libs.sbar.events import (
        BackgroundSourceType,
        SBARArtifactRef,
        SBARBackgroundSourceRef,
        SBARRequestPayload,
        SBARSituationInput,
        SituationArtifactType,
        SummarisationContext,
    )
    from services.pipeline_worker.app.services.sbar_orchestrator import (
        SBAROrchestrator,
    )

    encounter_id = str(state.get("encounter_id") or "")
    patient_id = str(state.get("patient_id") or "")
    run_id = str(state.get("run_id") or "")
    workflow_id = str(state.get("workflow_id") or state.get("plan_definition_id") or "")
    guideline_ids = list(state.get("guideline_ids") or [])
    referral_id = str(state.get("referral_id") or "").strip()
    document_reference_id = str(state.get("document_reference_id") or "").strip()
    assessment_id = _assessment_id(run_id, encounter_id)

    # Atlas: DI-43233166 / DO-FE95EA83 -- letter extract for Situation,
    # referral_assessment framing (never hardcode a cancer pathway).
    artifacts = [
        SBARArtifactRef(
            type=SituationArtifactType.encounter,
            id=encounter_id,
        ),
        SBARArtifactRef(
            type=SituationArtifactType.summarisation_context,
            context_value=SummarisationContext.referral_assessment,
        ),
    ]
    if referral_id:
        artifacts.append(
            SBARArtifactRef(
                type=SituationArtifactType.referral_request,
                id=referral_id,
            )
        )
    if document_reference_id:
        artifacts.append(
            SBARArtifactRef(
                type=SituationArtifactType.document_reference,
                id=document_reference_id,
            )
        )
    background = [
        SBARBackgroundSourceRef(
            type=BackgroundSourceType.encounter,
            id=encounter_id,
        )
    ]
    if document_reference_id:
        background.append(
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.document_reference,
                id=document_reference_id,
            )
        )
    payload = SBARRequestPayload(
        run_id=f"{run_id}:sbar",
        requested_by=state.get("requested_by"),
        tenant_id=state.get("tenant_id"),
        assessment_id=assessment_id,
        encounter_id=encounter_id,
        concern="Referral assessment SBAR for clinician review.",
        guideline_ids=guideline_ids,
        situation=SBARSituationInput(
            patient_id=patient_id,
            artifacts=artifacts,
        ),
        background=background,
        upstream_correlation_id=run_id,
        source_system="referral-assessment-pipeline",
        extra={
            "parent_run_id": run_id,
            "workflow_id": workflow_id,
            "chunk_ids": list(state.get("chunk_ids") or []),
            "referral_id": referral_id,
            "referral_reason": str(state.get("referral_reason") or "").strip(),
            "completeness_result": state.get("completeness_result"),
            "compliance_result": state.get("compliance_result"),
            "source_node_type": str(state.get("source_node_type") or "ReferralRequest"),
            "healthcare_service_id": state.get("healthcare_service_id"),
            "healthcare_service_name": state.get("healthcare_service_name"),
            "healthcare_service_specialty": state.get("healthcare_service_specialty"),
            "healthcare_service_spoa_id": state.get("healthcare_service_spoa_id"),
            "healthcare_service_missing": state.get("healthcare_service_missing"),
            "form_clinical_section": state.get("form_clinical_section"),
            "form_sections": _form_sections_from_state(state),
        },
    )
    result = await SBAROrchestrator(
        policy_runtime=_runtime_from_state(state),
        dry_run=bool(state.get("dry_run")),
    ).run(payload)

    completeness_result = state.get("completeness_result")
    if completeness_result:
        _persist_completeness(
            assessment_id,
            completeness_result,
            dry_run=bool(state.get("dry_run")),
        )

    pipeline_errors, pipeline_warnings = _partition_pipeline_messages(
        list(result.errors or [])
    )

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
        "errors": pipeline_errors,
        "warnings": pipeline_warnings,
        "review_status": "pending_review",
    }


def _runtime_from_state(state: SBARSubgraphState) -> Any | None:
    from libs.sbar.policy_runtime import runtime_from_state

    return runtime_from_state(dict(state))


def _count_completeness_failures(completeness_result: dict[str, Any]) -> int:
    missing = completeness_result.get("missing_groups") or []
    return sum(1 for g in missing if g.get("required"))


def _persist_completeness(
    assessment_id: str,
    completeness_result: dict[str, Any],
    dry_run: bool = False,
) -> None:
    if dry_run:
        logger.info("dry_run=True - skipping completeness persist")
        return
    try:
        from libs.cypher.sbar_assessment_queries import SET_ASSESSMENT_COMPLETENESS
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        try:
            client.run(
                SET_ASSESSMENT_COMPLETENESS,
                assessment_id=assessment_id,
                completeness_result_json=json.dumps(completeness_result),
                completeness_failed_count=_count_completeness_failures(
                    completeness_result
                ),
            )
        finally:
            client.close()
    except Exception as exc:
        logger.warning(
            "Could not persist completeness result for assessment %s: %s",
            assessment_id,
            exc,
        )


def build_sbar_subgraph() -> CompiledStateGraph:
    """Build and compile the SBAR orchestrator subgraph."""
    graph = StateGraph(SBARSubgraphState)
    graph.add_node("run_sbar", _run_sbar)
    graph.add_edge(START, "run_sbar")
    graph.add_edge("run_sbar", END)
    return graph.compile()
