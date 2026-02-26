"""ValueSet CRUD endpoints (FHIR R4B compatible)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.terminology_api.app.services import valueset_service

router = APIRouter()


@router.get("/ValueSet")
def search_valuesets(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    url: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count", ge=1, le=1000),
    _offset: int = Query(default=0, alias="_offset", ge=0),
):
    items, total = valueset_service.search_valuesets(
        name=name, status=status, url=url, count=_count, offset=_offset
    )
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": total,
        "entry": [{"resource": vs} for vs in items],
    }


@router.get("/ValueSet/{valueset_id}")
def get_valueset(valueset_id: str):
    vs = valueset_service.get_valueset(valueset_id)
    if not vs:
        raise HTTPException(status_code=404, detail=f"ValueSet/{valueset_id} not found")
    return vs


@router.put("/ValueSet/{valueset_id}")
def upsert_valueset(valueset_id: str, resource: Dict[str, Any]):
    return valueset_service.upsert_valueset(valueset_id, resource)


@router.delete("/ValueSet/{valueset_id}", status_code=204)
def delete_valueset(valueset_id: str):
    valueset_service.delete_valueset(valueset_id)


@router.get("/ValueSet/{valueset_id}/$expand")
def expand_valueset(valueset_id: str):
    vs = valueset_service.expand_valueset(valueset_id)
    if not vs:
        raise HTTPException(status_code=404, detail=f"ValueSet/{valueset_id} not found")
    return vs
