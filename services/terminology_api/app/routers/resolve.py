"""Hybrid coding resolution endpoint.

Accepts a list of clinical terms and returns ranked SNOMED candidates
using the three-branch hybrid resolver.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError
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
_RESOLVE_RETRYABLE_EXCEPTIONS = (
    ServiceUnavailable,
    SessionExpired,
    TransientError,
    OSError,
)
_RESOLVE_MAX_ATTEMPTS = 3
_RESOLVE_RETRY_DELAY_SECONDS = 0.2


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
    # Raw retrieval signals exposed for downstream consumers that need
    # to apply branch-specific thresholds (e.g. "accept exact-branch
    # hits regardless of surface match"). The `score` field above is
    # already a CALIBRATED ABSOLUTE confidence in [0.0, 1.0] derived
    # from these signals plus tag matching:
    #   had_exact_match -- True iff this candidate was hit by the
    #     exact branch (Term.normalized_form or SurfaceForm.normalized
    #     equality), the strongest possible lexical signal.
    #   lexical_raw   -- max raw lexical score across the exact +
    #     fulltext branches. Exact = 1.0/1.2; fulltext = Lucene BM25
    #     (typically 0-15).
    #   vector_raw    -- cosine similarity from the embedding branch
    #     (0.0 - 1.0). >= 0.85 indicates strong semantic match even
    #     when surface token overlap is low.
    had_exact_match: bool = False
    lexical_raw: float = 0.0
    vector_raw: float = 0.0


class ResolveResponse(BaseModel):
    results: dict[str, list[CandidateResponse]]


@router.post("/resolve", response_model=ResolveResponse)
def resolve_terms(body: ResolveRequest):
    """Resolve clinical terms to SNOMED codes using hybrid retrieval."""
    t0 = time.perf_counter()
    n_terms = len(body.terms)
    logger.info("[resolve] request  terms=%d  %s", n_terms, body.terms[:5])

    raw = None
    t_session = time.perf_counter()
    t_resolve = t_session
    for attempt in range(1, _RESOLVE_MAX_ATTEMPTS + 1):
        try:
            with _kg_client.session() as session:
                t_session = time.perf_counter()
                raw = _resolver.resolve_candidates(
                    body.terms,
                    neo4j_session=session,
                    expected_tags=body.expected_tags,
                )
                t_resolve = time.perf_counter()
                break
        except _RESOLVE_RETRYABLE_EXCEPTIONS as exc:
            if attempt == _RESOLVE_MAX_ATTEMPTS:
                logger.exception(
                    "[resolve] failed after retries  terms=%d  attempts=%d",
                    n_terms,
                    _RESOLVE_MAX_ATTEMPTS,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Terminology resolver is temporarily unavailable. Please retry.",
                ) from exc
            logger.warning(
                "[resolve] transient neo4j error  terms=%d  attempt=%d/%d  err=%s",
                n_terms,
                attempt,
                _RESOLVE_MAX_ATTEMPTS,
                exc,
            )
            time.sleep(_RESOLVE_RETRY_DELAY_SECONDS * attempt)

    if raw is None:
        # Defensive guard: raw should always be set on success or raise on failure.
        raise HTTPException(
            status_code=503,
            detail="Terminology resolver is temporarily unavailable. Please retry.",
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
                had_exact_match=c.had_exact_match,
                lexical_raw=c.lexical_raw,
                vector_raw=c.vector_raw,
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
