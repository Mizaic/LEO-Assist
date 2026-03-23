"""Hybrid coding resolution endpoint.

Accepts a list of clinical terms and returns ranked SNOMED candidates
using the three-branch hybrid resolver.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.services.coding_resolver import CodingResolver
from services.terminology_api.app.services.text_embedder import TerminologyTextEmbedder

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singletons — driver connection pool and resolver are created
# once at startup and reused across all requests, avoiding repeated TCP
# handshakes to AuraDB and repeated embedder warm-up.
_embedder = TerminologyTextEmbedder()
_kg_client = KnowledgeGraphClient()
_resolver = CodingResolver(embedder=_embedder)


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
    t0 = time.perf_counter()
    n_terms = len(body.terms)
    logger.info("[resolve] request  terms=%d  %s", n_terms, body.terms[:5])

    with _kg_client.session() as session:
        t_session = time.perf_counter()
        raw = _resolver.resolve_candidates(
            body.terms,
            neo4j_session=session,
            expected_tags=body.expected_tags,
        )
        t_resolve = time.perf_counter()

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

    t_end = time.perf_counter()
    resolved = sum(1 for v in results.values() if v)
    logger.info(
        "[resolve] done  terms=%d  resolved=%d  session=%.3fs  resolve=%.3fs  serialise=%.3fs  total=%.3fs",
        n_terms,
        resolved,
        t_session - t0,
        t_resolve - t_session,
        t_end - t_resolve,
        t_end - t0,
    )
    return ResolveResponse(results=results)
