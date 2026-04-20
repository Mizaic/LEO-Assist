"""Surface form CRUD tools on knowledge graph.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

from typing import Any

from services.api.app.models.neo4j_schema import (
    COUNT_SURFACE_FORMS,
    DELETE_SURFACE_FORM,
    LIST_SURFACE_FORMS,
    UPSERT_SURFACE_FORM_MAPPING,
)
from services.neo4j_mcp._client import knowledge_run


def search_surface_forms(
    q: str | None = None,
    concept_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    rows = knowledge_run(
        LIST_SURFACE_FORMS,
        q=q,
        concept_id=concept_id,
        limit=limit,
        offset=offset,
    )
    count_rows = knowledge_run(COUNT_SURFACE_FORMS, q=q, concept_id=concept_id)
    total = int(count_rows[0]["total"]) if count_rows else 0
    return {"items": rows, "count": len(rows), "total": total}


def get_surface_form(normalized: str) -> dict[str, Any]:
    rows = knowledge_run(
        LIST_SURFACE_FORMS,
        q=None,
        concept_id=None,
        limit=1000,
        offset=0,
    )
    matches = [row for row in rows if row.get("normalized") == normalized]
    return {"items": matches, "count": len(matches)}


def create_surface_form(
    normalized: str,
    form: str,
    concept_id: str,
    source: str = "manual",
    created_by: str = "mcp",
    confidence: float = 1.0,
    provenance: str = "mcp",
) -> dict[str, Any]:
    rows = knowledge_run(
        UPSERT_SURFACE_FORM_MAPPING,
        normalized=normalized,
        form=form,
        concept_id=concept_id,
        source=source,
        created_by=created_by,
        confidence=confidence,
        provenance=provenance,
    )
    return {"item": rows[0] if rows else None}


def update_surface_form(
    normalized: str,
    form: str,
    concept_id: str,
    source: str = "manual",
    created_by: str = "mcp",
    confidence: float = 1.0,
    provenance: str = "mcp_update",
) -> dict[str, Any]:
    return create_surface_form(
        normalized=normalized,
        form=form,
        concept_id=concept_id,
        source=source,
        created_by=created_by,
        confidence=confidence,
        provenance=provenance,
    )


def delete_surface_form(normalized: str) -> dict[str, Any]:
    rows_before = knowledge_run(
        LIST_SURFACE_FORMS,
        q=None,
        concept_id=None,
        limit=5000,
        offset=0,
    )
    existing = [row for row in rows_before if row.get("normalized") == normalized]
    knowledge_run(DELETE_SURFACE_FORM, normalized=normalized)
    return {"deleted": bool(existing), "deleted_count": len(existing)}


TOOLS = [
    {
        "name": "search_surface_forms",
        "description": "Search surface forms and linked concepts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "concept_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
        },
        "fn": search_surface_forms,
    },
    {
        "name": "get_surface_form",
        "description": "Get mappings for one normalized surface form.",
        "inputSchema": {
            "type": "object",
            "properties": {"normalized": {"type": "string"}},
            "required": ["normalized"],
        },
        "fn": get_surface_form,
    },
    {
        "name": "create_surface_form",
        "description": "Create or upsert surface form mapping.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "normalized": {"type": "string"},
                "form": {"type": "string"},
                "concept_id": {"type": "string"},
                "source": {"type": "string", "default": "manual"},
                "created_by": {"type": "string", "default": "mcp"},
                "confidence": {"type": "number", "default": 1.0},
                "provenance": {"type": "string", "default": "mcp"},
            },
            "required": ["normalized", "form", "concept_id"],
        },
        "fn": create_surface_form,
    },
    {
        "name": "update_surface_form",
        "description": "Update surface form mapping via upsert.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "normalized": {"type": "string"},
                "form": {"type": "string"},
                "concept_id": {"type": "string"},
                "source": {"type": "string", "default": "manual"},
                "created_by": {"type": "string", "default": "mcp"},
                "confidence": {"type": "number", "default": 1.0},
                "provenance": {"type": "string", "default": "mcp_update"},
            },
            "required": ["normalized", "form", "concept_id"],
        },
        "fn": update_surface_form,
    },
    {
        "name": "delete_surface_form",
        "description": "Delete a surface form node and all mappings.",
        "inputSchema": {
            "type": "object",
            "properties": {"normalized": {"type": "string"}},
            "required": ["normalized"],
        },
        "fn": delete_surface_form,
    },
]

