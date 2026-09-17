"""Roll durable-stage LLM usage onto PipelineRun and AuditEvent.

Atlas trace:
  DO: DO-4D2BEA1D
  DI: DI-CDF1C4D4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D2BEA1D")

The durable referral path writes per-stage metrics_json. SBAR also writes
a PipelineRun AuditEvent with SBAR-only tokens. Dashboard spend reads
that AuditEvent, so extract and coding spend vanished. This rollup
replaces audit-{run_id} with the sum of every stage.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

LIST_STAGE_METRICS_FOR_RUN = """
MATCH (r:PipelineRun {id: $run_id})-[:HAS_STAGE]->(s:PipelineStageRun)
RETURN s.step_id AS step_id, s.metrics_json AS metrics_json
"""

SET_PIPELINE_RUN_LLM_SPEND = """
MATCH (r:PipelineRun {id: $run_id})
SET r.llm_input_tokens = $llm_input_tokens,
    r.llm_output_tokens = $llm_output_tokens,
    r.llm_cached_tokens = $llm_cached_tokens,
    r.llm_calls = $llm_calls,
    r.llm_cost_usd = $llm_cost_usd,
    r.updated_at = datetime()
RETURN r.id AS id
"""

UPSERT_PIPELINE_RUN_AUDIT_SPEND = """
MERGE (ae:AuditEvent {id: $id})
ON CREATE SET ae.created_at = datetime()
SET ae.type = 'PipelineRun',
    ae.run_id = $run_id,
    ae.patient_id = $patient_id,
    ae.encounter_id = $encounter_id,
    ae.status = $status,
    ae.llm_input_tokens = $llm_input_tokens,
    ae.llm_output_tokens = $llm_output_tokens,
    ae.llm_cached_tokens = $llm_cached_tokens,
    ae.llm_calls = $llm_calls,
    ae.llm_cost_usd = $llm_cost_usd,
    ae.updated_at = datetime()
WITH ae
OPTIONAL MATCH (p:Patient {id: $patient_id})
FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
    MERGE (ae)-[:AUDIT_FOR]->(p)
)
RETURN ae.id AS id
"""


def _parse_metrics(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _usage_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    usage = metrics.get("llm_usage")
    return usage if isinstance(usage, dict) else {}


def sum_stage_llm_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Add llm_usage from every PipelineStageRun row."""
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    calls = 0
    cost_usd = 0.0
    for row in rows:
        usage = _usage_from_metrics(_parse_metrics(row.get("metrics_json")))
        input_tokens += max(0, int(usage.get("input_tokens") or 0))
        output_tokens += max(0, int(usage.get("output_tokens") or 0))
        cached_tokens += max(0, int(usage.get("cached_input_tokens") or 0))
        calls += max(0, int(usage.get("llm_calls") or 0))
        cost_usd += max(0.0, float(usage.get("cost_usd") or 0.0))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_tokens,
        "llm_calls": calls,
        "cost_usd": round(cost_usd, 6),
    }


def write_run_llm_spend_rollup(
    client: Any,
    *,
    run_id: str,
    patient_id: str,
    encounter_id: str = "",
    status: str = "completed",
) -> dict[str, Any]:
    """Persist full-run spend onto PipelineRun and AuditEvent audit-{run_id}."""
    rows = list(client.run(LIST_STAGE_METRICS_FOR_RUN, run_id=run_id) or [])
    totals = sum_stage_llm_usage(rows)
    spend = {
        "llm_input_tokens": totals["input_tokens"],
        "llm_output_tokens": totals["output_tokens"],
        "llm_cached_tokens": totals["cached_input_tokens"],
        "llm_calls": totals["llm_calls"],
        "llm_cost_usd": totals["cost_usd"],
    }
    client.run(SET_PIPELINE_RUN_LLM_SPEND, run_id=run_id, **spend)
    client.run(
        UPSERT_PIPELINE_RUN_AUDIT_SPEND,
        id=f"audit-{run_id}",
        run_id=run_id,
        patient_id=patient_id,
        encounter_id=encounter_id or "",
        status=status,
        **spend,
    )
    return totals


def maybe_write_run_llm_spend_rollup(
    client: Any,
    *,
    run_id: str,
    patient_id: str,
    encounter_id: str = "",
    status: str = "completed",
    next_action_ids: list[str] | None = None,
    stage_failed: bool = False,
) -> None:
    """Write the rollup when the durable run has no further steps."""
    if next_action_ids and not stage_failed:
        return
    try:
        write_run_llm_spend_rollup(
            client,
            run_id=run_id,
            patient_id=patient_id,
            encounter_id=encounter_id,
            status=status,
        )
    except Exception:
        logger.warning(
            "telemetry: failed to roll up LLM spend for run %s",
            run_id,
            exc_info=True,
        )
