"""LLM usage reporting tools from patient graph.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

import json
from typing import Any

from libs.cypher.model_config_queries import (
    GET_AUDIT_EVENT_SPEND,
    GET_AUDIT_EVENT_SPEND_TOTALS,
    GET_PATIENT_LLM_SPEND,
)
from services.neo4j_mcp._client import patient_run


def _parse_usage(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def get_patient_llm_spend(
    patient_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    rows = patient_run(
        GET_PATIENT_LLM_SPEND,
        patient_id=patient_id,
        from_date=from_date,
        to_date=to_date,
    )
    encounters: list[dict[str, Any]] = []
    total_input = 0
    total_output = 0
    total_cached = 0
    total_cost = 0.0
    for row in rows:
        usage = _parse_usage(row.get("llmUsageJson"))
        item = {
            "candidateId": row.get("candidateId", ""),
            "encounterId": row.get("encounterId", ""),
            "updatedAt": str(row.get("updatedAt") or ""),
            "modelName": row.get("modelName", ""),
            "inputTokens": int(usage.get("input_tokens", 0)),
            "outputTokens": int(usage.get("output_tokens", 0)),
            "cachedTokens": int(usage.get("cached_input_tokens", 0)),
            "costUsd": float(usage.get("cost_usd") or 0.0),
        }
        encounters.append(item)
        total_input += item["inputTokens"]
        total_output += item["outputTokens"]
        total_cached += item["cachedTokens"]
        total_cost += item["costUsd"]
    return {
        "patientId": patient_id,
        "encounters": encounters,
        "totals": {
            "inputTokens": total_input,
            "outputTokens": total_output,
            "cachedTokens": total_cached,
            "costUsd": round(total_cost, 6),
            "cacheHitRate": round(total_cached / total_input, 4) if total_input else 0.0,
        },
    }


def get_run_llm_spend(
    patient_id: str | None = None,
    org_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    params = {
        "patient_id": patient_id,
        "selected_org_id": org_id,
        "from_date": from_date,
        "to_date": to_date,
        "is_admin": True,
        "org_ids": [],
    }
    rows = patient_run(GET_AUDIT_EVENT_SPEND, **params, limit=limit)
    total_rows = patient_run(GET_AUDIT_EVENT_SPEND_TOTALS, **params)
    agg = total_rows[0] if total_rows else {}
    return {
        "runs": rows,
        "totals": {
            "runCount": int(agg.get("runCount") or 0),
            "inputTokens": int(agg.get("inputTokens") or 0),
            "outputTokens": int(agg.get("outputTokens") or 0),
            "cachedTokens": int(agg.get("cachedTokens") or 0),
            "costUsd": round(float(agg.get("costUsd") or 0.0), 6),
        },
    }


TOOLS = [
    {
        "name": "get_patient_llm_spend",
        "description": "Get per-encounter LLM token and cost spend for one patient.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
            },
            "required": ["patient_id"],
        },
        "fn": get_patient_llm_spend,
    },
    {
        "name": "get_run_llm_spend",
        "description": "Get per-run LLM spend from AuditEvent nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "org_id": {"type": "string"},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
        },
        "fn": get_run_llm_spend,
    },
]

