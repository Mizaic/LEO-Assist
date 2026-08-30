"""In-process referral dry-run: existing chunks only, no graph writes.

Loads :Chunk nodes already on the graph. Does not pull, convert, or
re-chunk. Does not start a PipelineRun or write facts, SBAR, or
assessments.

Atlas trace:
  DO: DO-C4EAEB41
  DI: DI-D044C8F1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C4EAEB41")
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from libs.referral_quality.dry_run_enrichment import enrich_dry_run_state
from libs.workflow.engine import ActionDefinition, WorkflowEngine
from libs.workflow.plan_manifest import PlanAction, PlanManifest, load_plan_manifest

_WRITE_CYPHER = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DETACH|FOREACH)\b",
    re.IGNORECASE,
)
_PLAN_ID = "pd-referral-assessment"
DEFAULT_REPORT_DIR = Path("tmp/referral-quality-dry-run")
_GUARD_INSTALLED = False


def install_dry_run_write_guard() -> None:
    """Fail closed: block Cypher mutations on every Neo4j client.run."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    from libs.neo4j_client import client as neo4j_client

    original = neo4j_client.run_with_retry

    def guarded(client: Any, query: str, **params: Any) -> list[dict[str, Any]]:
        if is_write_cypher(query):
            raise RuntimeError("dry-run blocked a Neo4j write")
        return original(client, query, **params)

    neo4j_client.run_with_retry = guarded
    try:
        from neo4j import Session

        original_session_run = Session.run

        def session_guarded(self: Any, query: Any, *args: Any, **kwargs: Any) -> Any:
            text = query if isinstance(query, str) else str(query)
            if is_write_cypher(text):
                raise RuntimeError("dry-run blocked a Neo4j write")
            return original_session_run(self, query, *args, **kwargs)

        Session.run = session_guarded  # type: ignore[method-assign]
    except Exception:
        pass
    _GUARD_INSTALLED = True


def is_write_cypher(query: str) -> bool:
    """True when a Cypher string would change the graph."""
    return bool(_WRITE_CYPHER.search(query or ""))


def build_dry_run_state(
    *,
    referral_id: str,
    patient_id: str,
    encounter_id: str,
    document_reference_id: str,
    chunk_ids: list[str],
    run_id: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    """Initial pipeline state for a no-writeback referral run."""
    return {
        "event_type": "referral-received",
        "plan_definition_id": _PLAN_ID,
        "workflow_id": _PLAN_ID,
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "referral_id": referral_id,
        "document_reference_id": document_reference_id,
        "chunk_ids": list(chunk_ids),
        "text_segmentation_mode": "document_chunks",
        "run_id": run_id,
        "mode": "referral_assessment",
        "output_target": "patient_graph",
        "source_node_type": "ReferralRequest",
        "source_node_id": referral_id,
        "dry_run": True,
        "tenant_id": tenant_id,
        "requested_by": "run_referral_inprocess.py --dry-run",
        "errors": [],
        "warnings": [],
    }


def resolve_existing_chunks(client: Any, referral_id: str) -> dict[str, Any]:
    """Load already-ingested chunks. Never backfill or rewrite ids."""
    from libs.patient_document_runs.chunk_resolver import resolve_pipeline_chunks
    from scripts.replay_referral import ReplayError, _resolve_referral_target

    try:
        target = _resolve_referral_target(client, referral_id)
    except ReplayError as exc:
        return {"target": None, "chunk_ids": [], "skip_reason": str(exc)}
    resolved = resolve_pipeline_chunks(
        client,
        document_reference_id=target.document_reference_id,
        referral_id=referral_id,
        backfill_legacy_ids=False,
    )
    chunk_ids = [str(c["id"]) for c in resolved.chunks]
    skip = "" if chunk_ids else "No existing chunks on the graph."
    return {"target": target, "chunk_ids": chunk_ids, "skip_reason": skip}


def read_run_context(
    client: Any, patient_id: str, document_reference_id: str
) -> dict[str, Any]:
    """Read encounter and tenant ids. Does not MERGE an Encounter."""
    from libs.patient_document_runs.queries import RESOLVE_DOCUMENT_RUN_CONTEXT

    rows = client.run(
        RESOLVE_DOCUMENT_RUN_CONTEXT,
        patient_id=patient_id,
        document_reference_id=document_reference_id,
    )
    return dict(rows[0]) if rows else {}


def manifest_to_actions(manifest: PlanManifest) -> list[ActionDefinition]:
    """Convert a pinned plan snapshot into WorkflowEngine actions."""
    return [_plan_action_to_definition(action) for action in manifest.actions]


def _plan_action_to_definition(action: PlanAction) -> ActionDefinition:
    related = action.related_actions
    if related and isinstance(related[0], str):
        related_ids = list(related)
    else:
        related_ids = [
            str(item.get("actionId") or "")
            for item in related
            if isinstance(item, dict)
        ]
    return ActionDefinition(
        action_id=action.action_id,
        subgraph_id=action.subgraph_id,
        trigger_type="",
        trigger_name=action.trigger_name,
        node_type=action.node_type,
        config=action.config,
        related_actions=related_ids,
        related_edges=list(action.related_edges),
        sequence=action.sequence,
    )


def _fact_row(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": entity.get("text"),
        "assertion": entity.get("assertion"),
        "label": entity.get("label") or entity.get("semantic_tag"),
        "concept_id": entity.get("concept_id")
        or (entity.get("coding") or {}).get("snomed_concept_id"),
        "term": entity.get("term") or entity.get("snomed_term"),
    }


def _fired_guidelines(state: dict[str, Any]) -> list[Any]:
    result = state.get("compliance_result") or {}
    if isinstance(result, dict):
        if result.get("fired"):
            return list(result["fired"])
        rules = result.get("matched_rules") or []
        if rules:
            return rules
    return []


def build_quality_report(referral_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Quality snapshot for one UBRN. No patient identifier fields."""
    entities = [e for e in (state.get("entities") or []) if isinstance(e, dict)]
    return {
        "referral_id": referral_id,
        "dry_run": True,
        "status": state.get("status") or state.get("sbar_status") or "completed",
        "chunk_ids": list(state.get("chunk_ids") or []),
        "facts": [_fact_row(e) for e in entities],
        "scope": {
            "completeness_domain": state.get("completeness_domain") or "",
            "completeness_subdomain": state.get("completeness_subdomain") or "",
            "healthcare_service_id": state.get("healthcare_service_id") or "",
            "primary_guideline_ids": list(state.get("primary_guideline_ids") or []),
            "patient_age": state.get("patient_age"),
            "patient_sex": state.get("patient_sex") or "",
        },
        "completeness": state.get("completeness_result") or {},
        "fired_guidelines": _fired_guidelines(state),
        "compliance_result": state.get("compliance_result") or {},
        "sbar_sections": state.get("sbar_sections") or {},
        "sbar_status": state.get("sbar_status") or "",
        "warnings": list(state.get("warnings") or []),
        "errors": list(state.get("errors") or []),
        "documents_written": int(state.get("documents_written") or 0),
    }


def dump_quality_report(
    report_dir: Path, referral_id: str, state: dict[str, Any]
) -> Path:
    """Write one JSON report. Filename is the UBRN only."""
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{referral_id}.json"
    path.write_text(json.dumps(build_quality_report(referral_id, state), indent=2))
    return path


async def run_dry_pipeline(
    client: Any,
    referral_id: str,
    *,
    report_dir: Path,
    timeout_s: int = 900,
) -> dict[str, Any]:
    """Run the referral plan in memory and dump a local quality report."""
    del timeout_s
    install_dry_run_write_guard()
    info = resolve_existing_chunks(client, referral_id)
    chunk_ids = list(info.get("chunk_ids") or [])
    target = info.get("target")
    if not chunk_ids or target is None:
        state = {
            "status": "skipped",
            "errors": [info.get("skip_reason") or "No existing chunks."],
            "chunk_ids": [],
        }
        path = dump_quality_report(report_dir, referral_id, state)
        return {"status": "skipped", "report_path": str(path), "chunk_count": 0}

    ctx = read_run_context(client, target.patient_id, target.document_reference_id)
    encounter_id = str(ctx.get("encounter_id") or f"{referral_id}:referral-assessment")
    state = build_dry_run_state(
        referral_id=referral_id,
        patient_id=target.patient_id,
        encounter_id=encounter_id,
        document_reference_id=target.document_reference_id,
        chunk_ids=chunk_ids,
        run_id=uuid.uuid4().hex,
        tenant_id=str(ctx.get("tenant_id") or ""),
    )
    enrich_dry_run_state(client, state)
    manifest = load_plan_manifest(_PLAN_ID)
    engine = WorkflowEngine()
    engine._sanitize_state = lambda raw: dict(raw)
    result = await engine.trace_run(manifest_to_actions(manifest), state)
    final = dict(result.get("final_state") or state)
    final["status"] = result.get("status") or final.get("status") or "completed"
    path = dump_quality_report(report_dir, referral_id, final)
    return {
        "status": final["status"],
        "report_path": str(path),
        "chunk_count": len(chunk_ids),
    }
