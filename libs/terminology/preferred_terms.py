"""Shared SNOMED preferred-term cache helpers.

This module centralizes concept-id -> preferred-term hydration using Redis-first
lookup with Neo4j fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "").strip()
SNOMED_PT_CACHE_TTL_SECONDS = int(os.getenv("SNOMED_PT_CACHE_TTL_SECONDS", "86400"))
_PT_CACHE_PREFIX = "snomed:pt:"
_CONNECT_TIMEOUT = 2
_SOCKET_TIMEOUT = 2

_cache_client: Any = None


def _get_cache_client():
    global _cache_client
    if _cache_client is not None:
        return _cache_client
    if not REDIS_URL:
        return None
    try:
        import redis

        _cache_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=_CONNECT_TIMEOUT,
            socket_timeout=_SOCKET_TIMEOUT,
        )
        return _cache_client
    except Exception:
        _cache_client = None
        return None


def _cache_key(concept_id: str) -> str:
    return f"{_PT_CACHE_PREFIX}{concept_id}"


def _safe_parse_json_array(raw: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def normalise_entity_for_display(entity: dict[str, Any]) -> dict[str, Any]:
    coding = entity.get("coding") if isinstance(entity.get("coding"), dict) else {}
    concept_id = str(
        entity.get("snomed_concept_id")
        or entity.get("concept_id")
        or coding.get("snomed_concept_id")
        or ""
    ).strip()
    snomed_term = str(
        entity.get("snomed_term")
        or entity.get("preferred_term")
        or entity.get("term")
        or coding.get("snomed_term")
        or ""
    ).strip()
    merged = dict(entity)
    if concept_id and not merged.get("snomed_concept_id"):
        merged["snomed_concept_id"] = concept_id
    if snomed_term and not merged.get("snomed_term"):
        merged["snomed_term"] = snomed_term
    return merged


def to_preferred_term(raw_term: str) -> str:
    """Convert FSN-like terms to preferred display term."""
    term = str(raw_term or "").strip()
    if not term:
        return ""
    return re.sub(r"\s*\([^)]+\)\s*$", "", term).strip() or term


def resolve_preferred_terms_for_concepts(
    session: Any,
    concept_ids: list[str],
) -> dict[str, str]:
    resolved_terms: dict[str, str] = {}
    if not concept_ids:
        return resolved_terms

    cache = _get_cache_client()
    unresolved_ids = sorted({cid for cid in concept_ids if cid})
    if cache and unresolved_ids:
        try:
            keys = [_cache_key(cid) for cid in unresolved_ids]
            cached_values = cache.mget(keys)
            misses: list[str] = []
            for concept_id, cached in zip(unresolved_ids, cached_values):
                cached_term = to_preferred_term(str(cached or "").strip())
                if cached_term:
                    resolved_terms[concept_id] = cached_term
                else:
                    misses.append(concept_id)
            unresolved_ids = misses
        except Exception:
            unresolved_ids = sorted({cid for cid in concept_ids if cid})

    if unresolved_ids:
        rows = session.run(
            "UNWIND $ids AS cid "
            "MATCH (c:Concept {id: cid}) "
            "RETURN c.id AS concept_id, "
            "coalesce(c.preferred_term, c.term, c.fsn, '') AS term",
            ids=unresolved_ids,
        )
        fresh_terms = {
            str(r["concept_id"]): to_preferred_term(str(r.get("term") or "").strip())
            for r in rows
            if r.get("concept_id")
        }
        resolved_terms.update({k: v for k, v in fresh_terms.items() if v})
        if cache and fresh_terms:
            try:
                pipe = cache.pipeline()
                for concept_id, term in fresh_terms.items():
                    if term:
                        pipe.setex(_cache_key(concept_id), SNOMED_PT_CACHE_TTL_SECONDS, term)
                pipe.execute()
            except Exception:
                logger.debug("Preferred-term cache write failed", exc_info=True)
    return resolved_terms


def hydrate_entities_json_items_with_pt_cache(
    session: Any,
    items: list[dict[str, Any]],
    entities_field: str = "entities_json",
) -> None:
    parsed_by_index: dict[int, list[dict[str, Any]]] = {}
    concept_ids: list[str] = []

    for idx, item in enumerate(items):
        entities = _safe_parse_json_array(str(item.get(entities_field) or "[]"))
        normalised = [normalise_entity_for_display(e) for e in entities]
        parsed_by_index[idx] = normalised
        for entity in normalised:
            concept_id = str(entity.get("snomed_concept_id") or "").strip()
            if concept_id:
                concept_ids.append(concept_id)

    if not parsed_by_index:
        return

    resolved_terms = resolve_preferred_terms_for_concepts(session, concept_ids)
    for idx, entities in parsed_by_index.items():
        hydrated: list[dict[str, Any]] = []
        for entity in entities:
            concept_id = str(entity.get("snomed_concept_id") or "").strip()
            if concept_id:
                term = resolved_terms.get(concept_id, "").strip()
                if term:
                    entity = dict(entity)
                    entity["snomed_term"] = term
            hydrated.append(entity)
        items[idx][entities_field] = json.dumps(hydrated)
