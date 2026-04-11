"""Terminology fulltext search endpoint."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from libs.cypher.terminology_queries import SEMANTIC_TAGS_QUERY
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.semantic_tag import normalise_semantic_tag
from services.terminology_api.app.queries.terminology import (
    TERMINOLOGY_SEARCH,
    TERMINOLOGY_SEARCH_FILTERED,
)

router = APIRouter()

# Characters that carry special meaning in the Lucene query-parser syntax.
# The SNOMED full-text index uses a standard analyser that already strips these
# during ingestion, so replacing them with spaces produces equivalent results
# while avoiding TokenMgrError / parse failures on inputs like
# "protein/creatinine ratio" (/ opens a regex literal in Lucene).
_LUCENE_SPECIAL = re.compile(r'[+\-!&|(){}\[\]^"~*?:\\/]')


def _sanitize_lucene_query(q: str) -> str:
    """Replace Lucene special chars with spaces to prevent query-parse errors."""
    sanitized = _LUCENE_SPECIAL.sub(" ", q)
    return re.sub(r" +", " ", sanitized).strip()


@router.get("/semantic-tags")
def list_semantic_tags():
    """Return all distinct SNOMED CT semantic tags present in the knowledge graph."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(SEMANTIC_TAGS_QUERY)
        return [r["semantic_tag"] for r in rows]
    finally:
        client.close()


@router.get("/search")
def search_terms(
    q: str = Query(min_length=1),
    limit: int = Query(default=15, ge=1, le=50),
    semantic_tag: list[str] | None = Query(default=None),
):
    """Fulltext search across SNOMED Terms in the Knowledge Graph."""
    safe_q = _sanitize_lucene_query(q)
    if not safe_q:
        raise HTTPException(status_code=422, detail="Query is empty after sanitisation")
    client = KnowledgeGraphClient()
    try:
        if semantic_tag:
            normalised_tags = sorted(
                {normalise_semantic_tag(tag) for tag in semantic_tag if str(tag).strip()}
            )
            return client.run(
                TERMINOLOGY_SEARCH_FILTERED, q=safe_q, limit=limit, tags=normalised_tags
            )
        return client.run(TERMINOLOGY_SEARCH, q=safe_q, limit=limit)
    finally:
        client.close()
