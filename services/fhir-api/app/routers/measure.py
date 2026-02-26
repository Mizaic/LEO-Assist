"""FHIR Measure CRUD and $evaluate-measure endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from services.fhir_api.app.services import measure_service

router = APIRouter()


@router.get("/Measure")
def search_measures(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    items, total = measure_service.search_measures(name=name, status=status, count=_count, offset=_offset)
    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entry": [{"resource": m} for m in items]}


@router.get("/Measure/{measure_id}")
def get_measure(measure_id: str):
    m = measure_service.get_measure(measure_id)
    if not m:
        raise HTTPException(404, f"Measure/{measure_id} not found")
    return m


@router.put("/Measure/{measure_id}")
def upsert_measure(measure_id: str, resource: Dict[str, Any]):
    return measure_service.upsert_measure(measure_id, resource)


@router.delete("/Measure/{measure_id}", status_code=204)
def delete_measure(measure_id: str):
    measure_service.delete_measure(measure_id)


@router.get("/Measure/{measure_id}/$evaluate-measure")
def evaluate_measure(
    measure_id: str,
    org_id: Optional[str] = Query(default=None),
    ods_code: Optional[str] = Query(default=None),
):
    params = {}
    if org_id:
        params["org_id"] = org_id
    if ods_code:
        params["ods_code"] = ods_code
    result = measure_service.evaluate_measure(measure_id, params)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
