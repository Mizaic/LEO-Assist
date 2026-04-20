"""Surface-form patching with Neo4j terminology lookup.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from __future__ import annotations

import re
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+")

LOOKUP_QUERY = """
MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE toLower(t.normalized_form) = $normalized AND c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(r:ReadCode)
RETURN c.id AS snomed_concept_id,
       c.fsn AS snomed_term,
       collect(DISTINCT r.code)[0] AS read_code
LIMIT 1
"""

BATCH_LOOKUP_QUERY = """
UNWIND $terms AS norm
OPTIONAL MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE toLower(t.normalized_form) = norm AND c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(r:ReadCode)
RETURN norm AS normalized,
       c.id AS snomed_concept_id,
       c.fsn AS snomed_term,
       collect(DISTINCT r.code)[0] AS read_code
"""

_EMPTY_CODING: dict[str, Any] = {
    "snomed_concept_id": None,
    "read_code": None,
    "snomed_term": None,
    "score": 0.0,
    "source": "neo4j_hybrid",
}


def normalize_surface(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def _build_result(text: str, normalized: str, record: dict | None) -> dict[str, Any]:
    if not record or not record.get("snomed_concept_id"):
        return {
            "text": text,
            "normalized_text": normalized,
            "coding": {**_EMPTY_CODING},
        }
    return {
        "text": text,
        "normalized_text": normalized,
        "coding": {
            "snomed_concept_id": record["snomed_concept_id"],
            "read_code": record.get("read_code"),
            "snomed_term": record.get("snomed_term"),
            "score": 1.0,
            "source": "neo4j_hybrid",
        },
    }


def patch_surface_term(text: str, neo4j_session) -> dict[str, Any]:
    normalized = normalize_surface(text)
    if not normalized:
        return _build_result(text, normalized, None)
    records = list(neo4j_session.run(LOOKUP_QUERY, normalized=normalized))
    return _build_result(text, normalized, dict(records[0]) if records else None)


def batch_patch_surface_terms(
    texts: list[str], neo4j_session
) -> dict[str, dict[str, Any]]:
    """Resolve many surface forms in a single UNWIND query.

    Returns a dict keyed by original surface text.
    """
    if not texts:
        return {}

    norm_map: dict[str, list[str]] = {}
    for t in texts:
        n = normalize_surface(t)
        if n:
            norm_map.setdefault(n, []).append(t)

    empty_results = {
        t: _build_result(t, normalize_surface(t), None)
        for t in texts
        if not normalize_surface(t)
    }

    if not norm_map:
        return empty_results

    records = list(neo4j_session.run(BATCH_LOOKUP_QUERY, terms=list(norm_map.keys())))
    resolved: dict[str, dict] = {}
    for r in records:
        row = dict(r)
        resolved[row["normalized"]] = row

    result: dict[str, dict[str, Any]] = {**empty_results}
    for norm, originals in norm_map.items():
        row = resolved.get(norm)
        for orig in originals:
            result[orig] = _build_result(orig, norm, row)
    return result
