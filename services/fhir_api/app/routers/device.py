"""FHIR Device CRUD endpoints (agent configuration store).

Atlas trace:
  DO: DO-34E24FA1
  DI: DI-1795254D, DI-710D5213
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-34E24FA1")
"""

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
    type: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:Device) "
            "WHERE ($status IS NULL OR d.status = $status) "
            "AND ($typeCode IS NULL OR d.typeCode = $typeCode) "
            "RETURN d.rawJson AS rawJson ORDER BY d.id LIMIT $limit",
            status=status,
            typeCode=type,
            limit=_count,
        )
        items = [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")]
        if name:
            items = [d for d in items if name.lower() in json.dumps(d).lower()]
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(items),
            "entry": [{"resource": d} for d in items],
        }
    finally:
        client.close()


@router.get("/Device/{device_id}")
def get_device(device_id: str):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:Device {id: $did}) RETURN d.rawJson AS rawJson LIMIT 1",
            did=device_id,
        )
        if not rows or not rows[0].get("rawJson"):
            raise HTTPException(404, f"Device/{device_id} not found")
        return json.loads(rows[0]["rawJson"])
    finally:
        client.close()


@router.put("/Device/{device_id}")
def upsert_device(device_id: str, resource: Dict[str, Any]):
    client = KnowledgeGraphClient()
    try:
        type_coding = (resource.get("type", {}).get("coding") or [{}])[0]
        client.run(
            "MERGE (d:Device {id: $did}) "
            "SET d.rawJson = $raw, d.status = $status, "
            "    d.typeCode = $typeCode, d.version = $version, "
            "    d.isGlobal = true",
            did=device_id,
            raw=json.dumps(resource),
            status=resource.get("status"),
            typeCode=type_coding.get("code"),
            version=(
                (resource.get("version") or [{}])[0].get("value")
                if resource.get("version")
                else None
            ),
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
