"""TrainingCandidate and GoldLabel tools on knowledge graph.

Atlas trace:
  DO: DO-4D608335
  DI: DI-760F5FB7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D608335")
"""

from __future__ import annotations

import json
from typing import Any

from libs.cypher.gold_label_queries import (
    COUNT_GOLD_LABELS_PAGE,
    DELETE_GOLD_LABEL_AND_RESET_CANDIDATE,
    GET_GOLD_LABEL_BY_CANDIDATE_ID,
    GET_GOLD_LABEL_BY_ID,
    GET_GOLD_LABEL_STATS,
    GET_GOLD_LABELS_PAGE,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from libs.cypher.training_candidate_queries import (
    COUNT_TRAINING_CANDIDATES_PAGE,
    DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
    GET_TRAINING_CANDIDATE_BY_ID,
    GET_TRAINING_CANDIDATE_STATS,
    GET_TRAINING_CANDIDATES_PAGE,
)
from libs.search.term_expansion import expand_search_terms
from services.neo4j_mcp._client import knowledge_run


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def list_training_candidates(
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    exclude_completed: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    terms = expand_search_terms(search)
    rows = knowledge_run(
        GET_TRAINING_CANDIDATES_PAGE,
        status=status,
        source=source,
        search=search,
        terms=terms,
        exclude_completed=exclude_completed,
        skip=offset,
        limit=limit,
    )
    count_rows = knowledge_run(
        COUNT_TRAINING_CANDIDATES_PAGE,
        status=status,
        source=source,
        search=search,
        terms=terms,
        exclude_completed=exclude_completed,
    )
    total = int(count_rows[0]["total"]) if count_rows else 0
    return {"items": rows, "count": len(rows), "total": total}


def get_training_candidate(candidate_id: str) -> dict[str, Any]:
    rows = knowledge_run(GET_TRAINING_CANDIDATE_BY_ID, candidate_id=candidate_id)
    return {"item": rows[0] if rows else None}


def delete_training_candidate(candidate_id: str) -> dict[str, Any]:
    rows = knowledge_run(DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS, candidate_id=candidate_id)
    return {"item": rows[0] if rows else None}


def get_training_stats() -> dict[str, Any]:
    rows = knowledge_run(GET_TRAINING_CANDIDATE_STATS)
    return {"item": rows[0] if rows else None}


def list_gold_labels(
    source: str | None = None,
    search: str | None = None,
    entity_label: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    terms = expand_search_terms(search)
    rows = knowledge_run(
        GET_GOLD_LABELS_PAGE,
        source=source,
        search=search,
        terms=terms,
        entity_label=entity_label,
        skip=offset,
        limit=limit,
    )
    count_rows = knowledge_run(
        COUNT_GOLD_LABELS_PAGE,
        source=source,
        search=search,
        terms=terms,
        entity_label=entity_label,
    )
    total = int(count_rows[0]["total"]) if count_rows else 0
    return {"items": rows, "count": len(rows), "total": total}


def get_gold_label(label_id: str) -> dict[str, Any]:
    rows = knowledge_run(GET_GOLD_LABEL_BY_ID, label_id=label_id)
    return {"item": rows[0] if rows else None}


def get_gold_label_by_candidate(candidate_id: str) -> dict[str, Any]:
    rows = knowledge_run(GET_GOLD_LABEL_BY_CANDIDATE_ID, candidate_id=candidate_id)
    return {"item": rows[0] if rows else None}


def update_gold_label_entities(label_id: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    rows = knowledge_run(
        UPDATE_GOLD_LABEL_ENTITIES,
        label_id=label_id,
        entities_json=_json_dump(entities),
    )
    return {"item": rows[0] if rows else None}


def delete_gold_label(label_id: str) -> dict[str, Any]:
    rows = knowledge_run(DELETE_GOLD_LABEL_AND_RESET_CANDIDATE, label_id=label_id)
    return {"item": rows[0] if rows else None}


def get_gold_stats() -> dict[str, Any]:
    rows = knowledge_run(GET_GOLD_LABEL_STATS)
    return {"item": rows[0] if rows else None}


TOOLS = [
    {
        "name": "list_training_candidates",
        "description": "List TrainingCandidate nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "source": {"type": "string"},
                "search": {"type": "string"},
                "exclude_completed": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
        },
        "fn": list_training_candidates,
    },
    {
        "name": "get_training_candidate",
        "description": "Get one TrainingCandidate by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
        "fn": get_training_candidate,
    },
    {
        "name": "delete_training_candidate",
        "description": "Delete one TrainingCandidate and linked artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
        "fn": delete_training_candidate,
    },
    {
        "name": "get_training_stats",
        "description": "Get TrainingCandidate status counts.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": get_training_stats,
    },
    {
        "name": "list_gold_labels",
        "description": "List GoldLabel nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "search": {"type": "string"},
                "entity_label": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
        },
        "fn": list_gold_labels,
    },
    {
        "name": "get_gold_label",
        "description": "Get one GoldLabel by label ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"label_id": {"type": "string"}},
            "required": ["label_id"],
        },
        "fn": get_gold_label,
    },
    {
        "name": "get_gold_label_by_candidate",
        "description": "Get latest GoldLabel for one candidate.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
        "fn": get_gold_label_by_candidate,
    },
    {
        "name": "update_gold_label_entities",
        "description": "Replace entities_json for one GoldLabel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label_id": {"type": "string"},
                "entities": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["label_id", "entities"],
        },
        "fn": update_gold_label_entities,
    },
    {
        "name": "delete_gold_label",
        "description": "Delete GoldLabel and reset candidate status to pending.",
        "inputSchema": {
            "type": "object",
            "properties": {"label_id": {"type": "string"}},
            "required": ["label_id"],
        },
        "fn": delete_gold_label,
    },
    {
        "name": "get_gold_stats",
        "description": "Get GoldLabel aggregate quality stats.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": get_gold_stats,
    },
]

