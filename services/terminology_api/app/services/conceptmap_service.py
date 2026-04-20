"""ConceptMap CRUD and $translate service for the Knowledge Graph.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")

Ported from VRB fhir-api/app/services/conceptmap_service.py.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.conceptmap import (
    CONCEPTMAP_COUNT,
    CONCEPTMAP_DELETE,
    CONCEPTMAP_GET,
    CONCEPTMAP_SEARCH,
    CONCEPTMAP_UPSERT,
)


def _first(records: list) -> Optional[Dict[str, Any]]:
    if not records:
        return None
    raw = records[0].get("rawJson")
    return json.loads(raw) if raw else None


def upsert_conceptmap(
    conceptmap_id: str, resource: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        params = {
            "conceptMapId": conceptmap_id,
            "rawJson": json.dumps(resource),
            "url": resource.get("url"),
            "name": resource.get("name"),
            "title": resource.get("title"),
            "status": resource.get("status", "active"),
            "version": resource.get("version"),
            "sourceUri": resource.get("sourceUri"),
            "targetUri": resource.get("targetUri"),
        }
        records = client.run(CONCEPTMAP_UPSERT, **params)
        return _first(records)
    finally:
        client.close()


def get_conceptmap(conceptmap_id: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        return _first(client.run(CONCEPTMAP_GET, conceptMapId=conceptmap_id))
    finally:
        client.close()


def delete_conceptmap(conceptmap_id: str) -> None:
    client = KnowledgeGraphClient()
    try:
        client.run(CONCEPTMAP_DELETE, conceptMapId=conceptmap_id)
    finally:
        client.close()


def search_conceptmaps(
    name: Optional[str] = None,
    status: Optional[str] = None,
    url: Optional[str] = None,
    count: int = 100,
    offset: int = 0,
) -> tuple[List[Dict[str, Any]], int]:
    client = KnowledgeGraphClient()
    try:
        count_records = client.run(CONCEPTMAP_COUNT, name=name, status=status, url=url)
        total = count_records[0].get("total") if count_records else 0
        records = client.run(
            CONCEPTMAP_SEARCH,
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


def translate_concept(
    conceptmap_id: str, code: str, system: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Simplified $translate: find target codes for a given source code."""
    cm = get_conceptmap(conceptmap_id)
    if not cm:
        return None

    matches: List[Dict[str, Any]] = []
    for group in cm.get("group") or []:
        if system and group.get("source") != system:
            continue
        for element in group.get("element") or []:
            if element.get("code") == code:
                for target in element.get("target") or []:
                    matches.append(
                        {
                            "equivalence": target.get("equivalence", "equivalent"),
                            "concept": {
                                "system": group.get("target", ""),
                                "code": target.get("code"),
                                "display": target.get("display"),
                            },
                        }
                    )

    return {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "result", "valueBoolean": len(matches) > 0},
            *[
                {
                    "name": "match",
                    "part": [
                        {"name": "equivalence", "valueCode": m["equivalence"]},
                        {"name": "concept", "valueCoding": m["concept"]},
                    ],
                }
                for m in matches
            ],
        ],
    }
