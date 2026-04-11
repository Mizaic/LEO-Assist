"""ConceptMap CRUD and $translate endpoints (FHIR R4B compatible)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.terminology_api.app.services import conceptmap_service

router = APIRouter()


@router.get("/ConceptMap")
def search_conceptmaps(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    url: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count", ge=1, le=1000),
    _offset: int = Query(default=0, alias="_offset", ge=0),
):
    items, total = conceptmap_service.search_conceptmaps(
        name=name, status=status, url=url, count=_count, offset=_offset
    )
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": total,
        "entry": [{"resource": cm} for cm in items],
    }


@router.get("/ConceptMap/{conceptmap_id}")
def get_conceptmap(conceptmap_id: str):
    cm = conceptmap_service.get_conceptmap(conceptmap_id)
    if not cm:
        raise HTTPException(
            status_code=404, detail=f"ConceptMap/{conceptmap_id} not found"
        )
    return cm


@router.put("/ConceptMap/{conceptmap_id}")
def upsert_conceptmap(conceptmap_id: str, resource: Dict[str, Any]):
    return conceptmap_service.upsert_conceptmap(conceptmap_id, resource)


@router.delete("/ConceptMap/{conceptmap_id}", status_code=204)
def delete_conceptmap(conceptmap_id: str):
    conceptmap_service.delete_conceptmap(conceptmap_id)


@router.get("/ConceptMap/{conceptmap_id}/$translate")
def translate_concept(
    conceptmap_id: str,
    code: str = Query(...),
    system: Optional[str] = Query(default=None),
):
    result = conceptmap_service.translate_concept(conceptmap_id, code, system)
    if not result:
        raise HTTPException(
            status_code=404, detail=f"ConceptMap/{conceptmap_id} not found"
        )
    return result
