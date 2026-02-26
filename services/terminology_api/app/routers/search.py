"""Terminology fulltext search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import TERMINOLOGY_SEARCH

router = APIRouter()


@router.get("/search")
def search_terms(
    q: str = Query(min_length=1),
    limit: int = Query(default=15, ge=1, le=50),
):
    """Fulltext search across SNOMED Terms in the Knowledge Graph."""
    client = KnowledgeGraphClient()
    try:
        return client.run(TERMINOLOGY_SEARCH, q=q, limit=limit)
    finally:
        client.close()
