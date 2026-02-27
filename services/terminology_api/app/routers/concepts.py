"""SNOMED concept hierarchy endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import DESCENDANTS_TEMPLATE

router = APIRouter()


class DescendantResult(BaseModel):
    snomed_concept_id: str
    term: str
    semantic_tag: Optional[str] = None


@router.get("/concepts/{concept_id}/descendants", response_model=List[DescendantResult])
def get_descendants(
    concept_id: str,
    depth: int = Query(default=3, ge=1, le=5, description="IS_A traversal depth"),
    limit: int = Query(default=300, ge=1, le=500, description="Maximum number of results"),
    semantic_tag: Optional[str] = Query(default=None, description="Filter by semantic tag"),
):
    """Return active SNOMED descendants of a concept via IS_A relationships."""
    query = DESCENDANTS_TEMPLATE.format(depth=int(depth))
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            query,
            concept_id=concept_id,
            semantic_tag=semantic_tag,
            limit=limit,
        )
        if rows is None:
            raise HTTPException(status_code=404, detail=f"Concept {concept_id} not found or has no descendants")
        return rows
    finally:
        client.close()
