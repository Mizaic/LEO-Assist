"""Tool wrappers for Validation Lab scenario brainstorm.

Atlas: DI-EB716E68 / DO-A0ADDB38

search_snomed wraps TerminologyClient.search. search_guidelines does a
title substring match over already-loaded guidelines (no full-text
recommendation search in V1).
"""

from __future__ import annotations

import logging
from typing import Any

from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)

_FETCH_LOADED = """
MATCH (g:Guideline)
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (ch)-[:HAS_RECOMMENDATION]->(r:Recommendation)
RETURN g.id AS code, g.title AS title,
       count(DISTINCT r) AS recommendation_count
ORDER BY g.id
LIMIT 500
"""


def _list_loaded_guidelines() -> list[dict[str, Any]]:
    from libs.neo4j_client.client import KnowledgeGraphClient

    neo = KnowledgeGraphClient()
    try:
        rows = neo.run(_FETCH_LOADED)
        return [
            {
                "code": str(r.get("code") or ""),
                "title": str(r.get("title") or ""),
                "recommendation_count": int(r.get("recommendation_count") or 0),
            }
            for r in rows
            if r.get("code")
        ]
    finally:
        neo.close()


def search_snomed(
    query: str,
    semantic_tags: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Search SNOMED candidates; return [] on empty query or client failure."""
    cleaned = str(query or "").strip()
    if not cleaned:
        return []
    try:
        client = TerminologyClient()
        rows = client.search(
            cleaned,
            limit=int(limit),
            semantic_tags=semantic_tags,
        )
    except Exception:
        logger.warning("search_snomed(%r) failed", cleaned, exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("concept_id") or row.get("conceptId") or "").strip()
        term = str(
            row.get("preferred_term") or row.get("term") or row.get("fsn") or ""
        ).strip()
        if not cid:
            continue
        out.append(
            {
                "concept_id": cid,
                "preferred_term": term,
                "semantic_tag": str(row.get("semantic_tag") or "").strip(),
            }
        )
    return out


def search_guidelines(query: str) -> list[dict[str, Any]]:
    """Case-insensitive title substring match over loaded guidelines."""
    cleaned = str(query or "").strip().lower()
    if not cleaned:
        return []
    try:
        rows = _list_loaded_guidelines()
    except Exception:
        logger.warning("search_guidelines(%r) failed", cleaned, exc_info=True)
        return []
    hits: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or "")
        code = str(row.get("code") or "")
        if cleaned in title.lower() or cleaned in code.lower():
            hits.append({"code": code, "title": title})
    return hits
