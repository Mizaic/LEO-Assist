"""Shared helpers for data quality query pack tools."""

from __future__ import annotations

from typing import Any

from services.neo4j_mcp._client import knowledge_run, patient_run
from services.neo4j_mcp.tools.query_pack_config import QUERY_POLICY


def _policy(query_id: str) -> dict[str, Any]:
    return QUERY_POLICY.get(query_id, {})


def _result(query_id: str, category: str, summary: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    policy = _policy(query_id)
    return {
        "query_id": query_id,
        "category": category,
        "summary": summary,
        "owner": policy.get("owner"),
        "sla_hours": policy.get("sla_hours"),
        "thresholds": policy.get("thresholds", {}),
        "action": policy.get("action", ""),
        "row_count": len(rows),
        "rows": rows,
    }


def run_patient(query: str, **params: Any) -> list[dict[str, Any]]:
    return patient_run(query, **params)


def run_knowledge(query: str, **params: Any) -> list[dict[str, Any]]:
    return knowledge_run(query, **params)

