"""Validation Lab run inspector snapshot (Neo4j + pinned plan).

Atlas trace:
  DO: DO-158BE606
  DI: DI-FE423B8D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
"""

from __future__ import annotations

import json
import os
from typing import Any

from libs.cypher.pipeline_stage_queries import (
    GET_PIPELINE_RUN_INSPECTOR,
    GET_PIPELINE_STAGE_DETAIL,
    LIST_PIPELINE_STAGE_RUNS_INSPECTOR,
)
from libs.validation_lab.pipeline import resolve_pipeline_run_id
from libs.validation_lab.stage_errors import (
    plain_english_pipeline_error,
    plain_english_pipeline_message,
    stage_errors_from_row,
    stage_warnings_from_row,
)
from libs.validation_lab.trace_events import keys_from_state
from libs.workflow.execution_manifest import manifest_from_json

_MAX_JSON_BYTES = max(32_768, int(os.getenv("LAB_INSPECTOR_MAX_JSON_BYTES", "262144")))

_LOAD_PLAN_RAW_BY_VERSION = """
MATCH (v:PlanDefinitionVersion)
WHERE v.id = $plan_version_id
   OR toString(v.versionId) = $plan_version_id
   OR ('v' + toString(v.versionId)) = $plan_version_id
RETURN v.rawJson AS plan_raw_json,
       v.versionId AS plan_version_number
LIMIT 1
"""

_LOAD_PLAN_RAW_BY_PLAN = """
MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_VERSION]->(v:PlanDefinitionVersion)
RETURN v.rawJson AS plan_raw_json,
       v.versionId AS plan_version_number
ORDER BY v.versionId DESC
LIMIT 1
"""


def _loads_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _truncate_json(raw: Any) -> tuple[Any, bool]:
    if raw is None:
        return None, False
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    if len(text.encode("utf-8")) <= _MAX_JSON_BYTES:
        return _loads_json(raw) if isinstance(raw, str) else raw, False
    return {"_truncated": True, "_preview": text[: _MAX_JSON_BYTES // 2]}, True


def _parse_plan_steps(raw_json: Any) -> list[dict[str, Any]]:
    plan = _loads_json(raw_json)
    actions = plan.get("action") or plan.get("actions") or []
    if not isinstance(actions, list):
        return []
    steps: list[dict[str, Any]] = []
    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id") or "")
        dynamic = action.get("_dynamicValues") or {}
        params = dynamic.get("params") if isinstance(dynamic, dict) else {}
        if not isinstance(params, dict):
            params = dynamic if isinstance(dynamic, dict) else {}
        steps.append(
            {
                "action_id": action_id,
                "subgraph_id": str(
                    (params or {}).get("subgraphId")
                    or action.get("code", {}).get("text")
                    or ""
                ),
                "node_type": str((params or {}).get("nodeType") or "action"),
                "sequence": idx,
                "durable_loads": list((params or {}).get("durableLoads") or []),
                "durable_persists": list((params or {}).get("durablePersists") or []),
            }
        )
    return steps


def _parse_plan_edges(raw_json: Any) -> list[dict[str, Any]]:
    """Extract canvas successor edges from PlanDefinition relatedAction."""
    plan = _loads_json(raw_json)
    actions = plan.get("action") or plan.get("actions") or []
    if not isinstance(actions, list):
        return []
    edges: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        target_id = str(action.get("id") or "").strip()
        if not target_id:
            continue
        for rel in action.get("relatedAction") or []:
            if not isinstance(rel, dict):
                continue
            source_id = str(rel.get("actionId") or "").strip()
            if not source_id:
                continue
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "relationship": str(rel.get("relationship") or "after-end"),
                }
            )
    return edges


def _load_plan_raw_from_knowledge_graph(
    *,
    plan_version_id: str,
    plan_id: str,
) -> tuple[Any, Any]:
    """Load PlanDefinitionVersion rawJson from the knowledge graph."""
    from libs.neo4j_client.client import KnowledgeGraphClient

    kg = KnowledgeGraphClient()
    try:
        version_key = (plan_version_id or "").strip()
        if version_key:
            rows = kg.run(_LOAD_PLAN_RAW_BY_VERSION, plan_version_id=version_key)
            if rows and rows[0].get("plan_raw_json"):
                return rows[0]["plan_raw_json"], rows[0].get("plan_version_number")
        plan_key = (plan_id or "").strip()
        if plan_key:
            rows = kg.run(_LOAD_PLAN_RAW_BY_PLAN, plan_id=plan_key)
            if rows and rows[0].get("plan_raw_json"):
                return rows[0]["plan_raw_json"], rows[0].get("plan_version_number")
    finally:
        kg.close()
    return None, None


def _resolve_plan_raw_json(
    row: dict[str, Any],
    *,
    run: dict[str, Any],
    case: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[Any, Any]:
    """Prefer patient-graph pin; fall back to knowledge graph by version id."""
    raw = row.get("plan_raw_json")
    version_number = row.get("plan_version_number")
    if raw:
        return raw, version_number

    plan_id = str(row.get("plan_id") or run.get("plan_id") or case.get("plan_id") or "")
    plan_version_id = str(
        row.get("plan_version_id") or manifest.get("plan_version_id") or ""
    )
    return _load_plan_raw_from_knowledge_graph(
        plan_version_id=plan_version_id,
        plan_id=plan_id,
    )


def _plan_steps_from_spans(stage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Last-resort plan steps so the flow map can render recorded stage spans."""
    steps: list[dict[str, Any]] = []
    for idx, row in enumerate(stage_rows or []):
        step_id = str(row.get("step_id") or "").strip()
        if not step_id:
            continue
        steps.append(
            {
                "action_id": step_id,
                "subgraph_id": str(row.get("event_type") or ""),
                "node_type": "action",
                "sequence": idx,
                "durable_loads": [],
                "durable_persists": [],
            }
        )
    return steps


def _span_row(row: dict[str, Any]) -> dict[str, Any]:
    input_obj = _loads_json(row.get("input_json"))
    output_obj = _loads_json(row.get("output_json"))
    errors = stage_errors_from_row(row)
    warnings = stage_warnings_from_row(row)
    return {
        "step_id": str(row.get("step_id") or ""),
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or "pending"),
        "worker_id": str(row.get("worker_id") or ""),
        "started_at": str(row.get("started_at") or ""),
        "completed_at": str(row.get("completed_at") or ""),
        "attempt": int(row.get("attempt") or 1),
        "input_keys": keys_from_state(input_obj),
        "output_keys": keys_from_state(output_obj),
        "errors": errors,
        "warnings": warnings,
        "error_summary": plain_english_pipeline_error(errors[0])
        if errors
        else "",
        "warning_summary": plain_english_pipeline_message(warnings[0])
        if warnings
        else "",
    }


def get_run_inspector(
    client: Any,
    *,
    case_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Build inspector snapshot for a Validation Lab run."""
    from libs.validation_lab.service import get_run

    packed = get_run(client, case_id, run_id)
    run = packed["run"]
    case = packed["case"]
    pipeline_run_id = resolve_pipeline_run_id(
        client,
        case=case,
        run=run,
        run_id=run_id,
    )
    rows = client.run(GET_PIPELINE_RUN_INSPECTOR, run_id=pipeline_run_id)
    row = (rows or [{}])[0] if rows else {}
    stage_rows = client.run(
        LIST_PIPELINE_STAGE_RUNS_INSPECTOR,
        run_id=pipeline_run_id,
    )
    manifest = manifest_from_json(str(row.get("execution_manifest_json") or ""))
    plan_id = str(row.get("plan_id") or run.get("plan_id") or case.get("plan_id") or "")
    plan_version_id = str(
        row.get("plan_version_id") or manifest.get("plan_version_id") or ""
    )
    plan_raw_json, plan_version_number = _resolve_plan_raw_json(
        row,
        run=run,
        case=case,
        manifest=manifest,
    )
    plan_steps = _parse_plan_steps(plan_raw_json)
    if not plan_steps and stage_rows:
        plan_steps = _plan_steps_from_spans(stage_rows)
    return {
        "lab_run_id": run_id,
        "pipeline_run_id": pipeline_run_id,
        "lab_status": str(run.get("status") or ""),
        "pipeline_status": str(row.get("pipeline_status") or "queued"),
        "plan_id": plan_id,
        "plan_version_id": plan_version_id,
        "plan_version_number": plan_version_number or row.get("plan_version_number"),
        "execution_manifest": manifest,
        "plan_steps": plan_steps,
        "plan_edges": _parse_plan_edges(plan_raw_json),
        "spans": [_span_row(r) for r in (stage_rows or [])],
        "sse_path": f"/api/pipeline/progress/{pipeline_run_id}",
    }


def get_stage_detail(
    client: Any,
    *,
    case_id: str,
    run_id: str,
    step_id: str,
) -> dict[str, Any]:
    """Return full stage input/output JSON for the data-flow tab."""
    from libs.validation_lab.service import get_run

    packed = get_run(client, case_id, run_id)
    pipeline_run_id = resolve_pipeline_run_id(
        client,
        case=packed["case"],
        run=packed["run"],
        run_id=run_id,
    )
    rows = client.run(
        GET_PIPELINE_STAGE_DETAIL,
        run_id=pipeline_run_id,
        step_id=step_id,
    )
    if not rows:
        raise KeyError(f"Pipeline stage not found: {step_id}")
    row = rows[0]
    input_data, input_truncated = _truncate_json(row.get("input_json"))
    output_data, output_truncated = _truncate_json(row.get("output_json"))
    errors = stage_errors_from_row(row)
    warnings = stage_warnings_from_row(row)
    return {
        "step_id": str(row.get("step_id") or step_id),
        "status": str(row.get("status") or ""),
        "worker_id": str(row.get("worker_id") or ""),
        "started_at": str(row.get("started_at") or ""),
        "completed_at": str(row.get("completed_at") or ""),
        "attempt": int(row.get("attempt") or 1),
        "input": input_data,
        "output": output_data,
        "errors": errors,
        "warnings": warnings,
        "error_summary": plain_english_pipeline_error(errors[0])
        if errors
        else "",
        "warning_summary": plain_english_pipeline_message(warnings[0])
        if warnings
        else "",
        "truncated": input_truncated or output_truncated,
    }
