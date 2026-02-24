"""Terminology search endpoint against coding graph."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db.neo4j_client import CodingGraphClient
from app.models.neo4j_schema import TERMINOLOGY_SEARCH


router = APIRouter(prefix="/terminology", tags=["terminology"])


@router.get("/search")
def search_terms(q: str = Query(min_length=1), limit: int = Query(default=15, ge=1, le=50)):
    client = CodingGraphClient()
    try:
        return client.run(TERMINOLOGY_SEARCH, q=q, limit=limit)
    finally:
        client.close()
