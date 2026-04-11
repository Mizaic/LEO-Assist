"""ValueSet CRUD service for the Knowledge Graph.

Ported from VRB fhir-api/app/services/valueset_service.py.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.valueset import (
    VALUESET_COUNT,
    VALUESET_DELETE,
    VALUESET_GET,
    VALUESET_GET_BY_URL,
    VALUESET_SEARCH,
    VALUESET_UPSERT,
)


def _first(records: list) -> Optional[Dict[str, Any]]:
    if not records:
        return None
    raw = records[0].get("rawJson")
    return json.loads(raw) if raw else None


def upsert_valueset(
    valueset_id: str, resource: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        params = {
            "valueSetId": valueset_id,
            "rawJson": json.dumps(resource),
            "url": resource.get("url"),
            "name": resource.get("name"),
            "title": resource.get("title"),
            "status": resource.get("status", "active"),
            "version": resource.get("version"),
        }
        records = client.run(VALUESET_UPSERT, **params)
        return _first(records)
    finally:
        client.close()


def get_valueset(valueset_id: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        return _first(client.run(VALUESET_GET, valueSetId=valueset_id))
    finally:
        client.close()


def get_valueset_by_url(url: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        return _first(client.run(VALUESET_GET_BY_URL, url=url))
    finally:
        client.close()


def delete_valueset(valueset_id: str) -> None:
    client = KnowledgeGraphClient()
    try:
        client.run(VALUESET_DELETE, valueSetId=valueset_id)
    finally:
        client.close()


def search_valuesets(
    name: Optional[str] = None,
    status: Optional[str] = None,
    url: Optional[str] = None,
    count: int = 100,
    offset: int = 0,
) -> tuple[List[Dict[str, Any]], int]:
    client = KnowledgeGraphClient()
    try:
        count_records = client.run(VALUESET_COUNT, name=name, status=status, url=url)
        total = count_records[0].get("total") if count_records else 0
        records = client.run(
            VALUESET_SEARCH,
            name=name,
            status=status,
            url=url,
            limit=count,
            offset=offset,
        )
        items = [json.loads(r["rawJson"]) for r in records if r.get("rawJson")]
        return items, total
    finally:
        client.close()


def expand_valueset(valueset_id: str) -> Optional[Dict[str, Any]]:
    """Simplified $expand — flatten compose.include into expansion.contains."""
    vs = get_valueset(valueset_id)
    if not vs:
        return None

    contains: List[Dict[str, Any]] = []
    for include in (vs.get("compose") or {}).get("include") or []:
        system = include.get("system", "")
        for concept in include.get("concept") or []:
            entry: Dict[str, Any] = {
                "system": system,
                "code": concept.get("code"),
                "display": concept.get("display"),
            }
            designations = concept.get("designation") or []
            if designations:
                entry["designation"] = designations
            contains.append(entry)

    vs["expansion"] = {
        "identifier": f"urn:uuid:{valueset_id}-expansion",
        "total": len(contains),
        "contains": contains,
    }
    return vs
