"""Hybrid coding resolution endpoint.

Accepts a list of clinical terms and returns ranked SNOMED candidates
using the three-branch hybrid resolver.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.services.coding_resolver import CodingResolver

router = APIRouter()


class ResolveRequest(BaseModel):
    terms: list[str] = Field(..., min_length=1)
    expected_tags: Optional[dict[str, str]] = None


class CandidateResponse(BaseModel):
    snomed_concept_id: str | None
    snomed_term: str | None
    semantic_tag: str | None = None
    read_code: str | None
    score: float
    source: str


class ResolveResponse(BaseModel):
    results: dict[str, list[CandidateResponse]]


@router.post("/resolve", response_model=ResolveResponse)
def resolve_terms(body: ResolveRequest):
    """Resolve clinical terms to SNOMED codes using hybrid retrieval."""
    client = KnowledgeGraphClient()
    try:
        resolver = CodingResolver()
        with client.session() as session:
            raw = resolver.resolve_candidates(
                body.terms,
                neo4j_session=session,
                expected_tags=body.expected_tags,
            )
        results = {
            text: [
                CandidateResponse(
                    snomed_concept_id=c.snomed_concept_id,
                    snomed_term=c.snomed_term,
                    semantic_tag=c.semantic_tag,
                    read_code=c.read_code,
                    score=c.score,
                    source=c.source,
                )
                for c in candidates
            ]
            for text, candidates in raw.items()
        }
        return ResolveResponse(results=results)
    finally:
        client.close()
