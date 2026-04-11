"""FHIR Library CRUD service for the Knowledge Graph."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from libs.neo4j_client.client import KnowledgeGraphClient


def get_library(library_id: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (l:Library {id: $lid}) RETURN l.rawJson AS rawJson LIMIT 1",
            lid=library_id,
        )
        return (
            json.loads(rows[0]["rawJson"]) if rows and rows[0].get("rawJson") else None
        )
    finally:
        client.close()


def upsert_library(
    library_id: str, resource: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (l:Library {id: $lid}) "
            "SET l.rawJson = $raw, l.name = $name, l.status = $status, "
            "    l.isGlobal = true",
            lid=library_id,
            raw=json.dumps(resource),
            name=resource.get("name"),
            status=resource.get("status", "active"),
        )
        return resource
    finally:
        client.close()


def delete_library(library_id: str) -> None:
    client = KnowledgeGraphClient()
    try:
        client.run("MATCH (l:Library {id: $lid}) DETACH DELETE l", lid=library_id)
    finally:
        client.close()


def search_libraries(
    name: Optional[str] = None,
    status: Optional[str] = None,
    count: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    client = KnowledgeGraphClient()
    try:
        count_rows = client.run(
            "MATCH (l:Library) WHERE ($name IS NULL OR l.name CONTAINS $name) "
            "AND ($status IS NULL OR l.status = $status) RETURN count(l) AS total",
            name=name,
            status=status,
        )
        total = count_rows[0]["total"] if count_rows else 0
        rows = client.run(
            "MATCH (l:Library) WHERE ($name IS NULL OR l.name CONTAINS $name) "
            "AND ($status IS NULL OR l.status = $status) "
            "RETURN l.rawJson AS rawJson ORDER BY l.name SKIP $offset LIMIT $limit",
            name=name,
            status=status,
            offset=offset,
            limit=count,
        )
        return [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")], total
    finally:
        client.close()
