"""Raw Cypher execution tools."""

from __future__ import annotations

from typing import Any

from services.neo4j_mcp._client import knowledge_run, patient_run

ROW_LIMIT = 200


def _cap_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) <= ROW_LIMIT:
        return rows
    return rows[:ROW_LIMIT]


def run_cypher_patient(
    query: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Cypher on patient graph with capped row output."""
    rows = patient_run(query, **(params or {}))
    return {"rows": _cap_rows(rows), "row_count": len(rows), "capped": len(rows) > ROW_LIMIT}


def run_cypher_knowledge(
    query: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Cypher on knowledge graph with capped row output."""
    rows = knowledge_run(query, **(params or {}))
    return {"rows": _cap_rows(rows), "row_count": len(rows), "capped": len(rows) > ROW_LIMIT}


TOOLS = [
    {
        "name": "run_cypher_patient",
        "description": "Run raw Cypher against patient graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["query"],
        },
        "fn": run_cypher_patient,
    },
    {
        "name": "run_cypher_knowledge",
        "description": "Run raw Cypher against knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["query"],
        },
        "fn": run_cypher_knowledge,
    },
]

