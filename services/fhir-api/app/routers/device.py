"""FHIR Device CRUD endpoints (agent configuration store)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import KnowledgeGraphClient

router = APIRouter()


@router.get("/Device")
def search_devices(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:Device) WHERE ($name IS NULL OR d.name CONTAINS $name) "
            "AND ($status IS NULL OR d.status = $status) "
            "RETURN d.rawJson AS rawJson ORDER BY d.name LIMIT $limit",
            name=name, status=status, limit=_count,
        )
        items = [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")]
        return {"resourceType": "Bundle", "type": "searchset", "total": len(items), "entry": [{"resource": d} for d in items]}
    finally:
        client.close()


@router.get("/Device/{device_id}")
def get_device(device_id: str):
    client = KnowledgeGraphClient()
    try:
        rows = client.run("MATCH (d:Device {id: $did}) RETURN d.rawJson AS rawJson LIMIT 1", did=device_id)
        if not rows or not rows[0].get("rawJson"):
            raise HTTPException(404, f"Device/{device_id} not found")
        return json.loads(rows[0]["rawJson"])
    finally:
        client.close()


@router.put("/Device/{device_id}")
def upsert_device(device_id: str, resource: Dict[str, Any]):
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (d:Device {id: $did}) SET d.rawJson = $raw, d.name = $name, d.status = $status",
            did=device_id, raw=json.dumps(resource), name=resource.get("deviceName", [{}])[0].get("name") if resource.get("deviceName") else None, status=resource.get("status"),
        )
        return resource
    finally:
        client.close()


@router.delete("/Device/{device_id}", status_code=204)
def delete_device(device_id: str):
    client = KnowledgeGraphClient()
    try:
        client.run("MATCH (d:Device {id: $did}) DETACH DELETE d", did=device_id)
    finally:
        client.close()
