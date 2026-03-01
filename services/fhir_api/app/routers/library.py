"""FHIR Library CRUD endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from services.fhir_api.app.services import library_service

router = APIRouter()


@router.get("/Library")
def search_libraries(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    items, total = library_service.search_libraries(name=name, status=status, count=_count, offset=_offset)
    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entry": [{"resource": l} for l in items]}


@router.get("/Library/{library_id}")
def get_library(library_id: str):
    l = library_service.get_library(library_id)
    if not l:
        raise HTTPException(404, f"Library/{library_id} not found")
    return l


@router.put("/Library/{library_id}")
def upsert_library(library_id: str, resource: Dict[str, Any]):
    return library_service.upsert_library(library_id, resource)


@router.delete("/Library/{library_id}", status_code=204)
def delete_library(library_id: str):
    library_service.delete_library(library_id)
