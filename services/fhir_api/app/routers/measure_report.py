"""FHIR MeasureReport CRUD endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import KnowledgeGraphClient

router = APIRouter()


@router.get("/MeasureReport")
def search_reports(
    measure: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (r:MeasureReport) "
            "WHERE ($measure IS NULL OR r.measure CONTAINS $measure) "
            "AND ($status IS NULL OR r.status = $status) "
            "RETURN r.rawJson AS rawJson "
            "ORDER BY r.periodEnd DESC SKIP $offset LIMIT $limit",
            measure=measure, status=status, offset=_offset, limit=_count,
        )
        items = [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")]
        return {"resourceType": "Bundle", "type": "searchset", "total": len(items), "entry": [{"resource": i} for i in items]}
    finally:
        client.close()


@router.get("/MeasureReport/{report_id}")
def get_report(report_id: str):
    client = KnowledgeGraphClient()
    try:
        rows = client.run("MATCH (r:MeasureReport {id: $rid}) RETURN r.rawJson AS rawJson LIMIT 1", rid=report_id)
        if not rows or not rows[0].get("rawJson"):
            raise HTTPException(404, f"MeasureReport/{report_id} not found")
        return json.loads(rows[0]["rawJson"])
    finally:
        client.close()


@router.put("/MeasureReport/{report_id}")
def upsert_report(report_id: str, resource: Dict[str, Any]):
    client = KnowledgeGraphClient()
    try:
        period = resource.get("period", {})
        client.run(
            "MERGE (r:MeasureReport {id: $rid}) "
            "SET r.rawJson = $raw, r.status = $status, r.measure = $measure, "
            "    r.type = $type, r.periodStart = $periodStart, r.periodEnd = $periodEnd, "
            "    r.tenantId = $tenantId",
            rid=report_id,
            raw=json.dumps(resource),
            status=resource.get("status"),
            measure=resource.get("measure"),
            type=resource.get("type"),
            periodStart=period.get("start"),
            periodEnd=period.get("end"),
            tenantId=resource.get("meta", {}).get("tag", [{}])[0].get("code") if resource.get("meta", {}).get("tag") else None,
        )
        return resource
    finally:
        client.close()


@router.delete("/MeasureReport/{report_id}", status_code=204)
def delete_report(report_id: str):
    client = KnowledgeGraphClient()
    try:
        client.run("MATCH (r:MeasureReport {id: $rid}) DETACH DELETE r", rid=report_id)
    finally:
        client.close()
