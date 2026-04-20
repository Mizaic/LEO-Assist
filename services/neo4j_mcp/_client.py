"""Shared Neo4j client helpers for MCP tools.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient


def _as_dict_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """Convert Neo4j rows into plain dictionaries."""
    result: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            result.append(dict(row))
            continue
        if hasattr(row, "data"):
            result.append(dict(row.data()))
            continue
        result.append(dict(row))
    return result


def patient_run(query: str, **params: Any) -> list[dict[str, Any]]:
    """Execute Cypher on the patient graph and return dict rows."""
    client = PatientGraphClient()
    try:
        return _as_dict_rows(client.run(query, **params))
    finally:
        client.close()


def knowledge_run(query: str, **params: Any) -> list[dict[str, Any]]:
    """Execute Cypher on the knowledge graph and return dict rows."""
    client = KnowledgeGraphClient()
    try:
        return _as_dict_rows(client.run(query, **params))
    finally:
        client.close()

