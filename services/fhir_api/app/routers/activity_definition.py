"""FHIR ActivityDefinition CRUD endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import KnowledgeGraphClient

router = APIRouter()


@router.get("/ActivityDefinition")
def search_activity_definitions(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (ad:ActivityDefinition) "
            "WHERE ($status IS NULL OR ad.status = $status) "
            "RETURN ad.rawJson AS rawJson "
            "ORDER BY ad.name "
            "SKIP $offset LIMIT $limit",
            status=status, offset=_offset, limit=_count,
        )
        items = [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")]
        if name:
            items = [a for a in items if name.lower() in (a.get("name") or "").lower()]
        total_rows = client.run(
            "MATCH (ad:ActivityDefinition) "
            "WHERE ($status IS NULL OR ad.status = $status) "
            "RETURN count(ad) AS total",
            status=status,
        )
        total = total_rows[0]["total"] if total_rows else len(items)
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": total,
            "entry": [{"resource": a} for a in items],
        }
    finally:
        client.close()


@router.get("/ActivityDefinition/{activity_id}")
def get_activity_definition(activity_id: str):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (ad:ActivityDefinition {id: $aid}) RETURN ad.rawJson AS rawJson LIMIT 1",
            aid=activity_id,
        )
        if not rows or not rows[0].get("rawJson"):
            raise HTTPException(404, f"ActivityDefinition/{activity_id} not found")
        return json.loads(rows[0]["rawJson"])
    finally:
        client.close()


@router.put("/ActivityDefinition/{activity_id}")
def upsert_activity_definition(activity_id: str, resource: Dict[str, Any]):
    resource["id"] = activity_id
    resource.setdefault("resourceType", "ActivityDefinition")

    dynamic_values = resource.get("dynamicValue", [])
    subgraph_id = resource.get("_subgraphId", "")

    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (ad:ActivityDefinition {id: $aid}) "
            "SET ad.rawJson = $raw, ad.status = $status, "
            "    ad.name = $name, ad.subgraphId = $sgid, "
            "    ad.dynamicValues = $dv, ad.isGlobal = true",
            aid=activity_id,
            raw=json.dumps(resource),
            status=resource.get("status"),
            name=resource.get("name"),
            sgid=subgraph_id,
            dv=json.dumps({v["path"]: v.get("expression", {}).get("expression") for v in dynamic_values}) if dynamic_values else None,
        )
        return resource
    finally:
        client.close()


@router.delete("/ActivityDefinition/{activity_id}", status_code=204)
def delete_activity_definition(activity_id: str):
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (ad:ActivityDefinition {id: $aid}) DETACH DELETE ad",
            aid=activity_id,
        )
    finally:
        client.close()
