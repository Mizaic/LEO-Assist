"""Resolve extracted terms to Read/SNOMED candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.term_patcher import normalize_surface


_CANDIDATE_QUERY = """
UNWIND $terms AS norm
OPTIONAL MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE toLower(t.normalized_form) = norm AND c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(r:ReadCode)
RETURN norm AS normalized,
       c.id AS snomed_concept_id,
       c.fsn AS snomed_term,
       collect(DISTINCT r.code)[0] AS read_code
"""


@dataclass(frozen=True)
class CodingCandidate:
    snomed_concept_id: str | None
    snomed_term: str | None
    read_code: str | None
    score: float
    source: str


class CodingResolver:
    def resolve_candidates(
        self,
        term_texts: list[str],
        *,
        neo4j_session,
    ) -> dict[str, list[CodingCandidate]]:
        if not term_texts:
            return {}

        norm_to_originals: dict[str, list[str]] = {}
        for text in term_texts:
            norm = normalize_surface(text)
            if not norm:
                continue
            norm_to_originals.setdefault(norm, []).append(text)
        if not norm_to_originals:
            return {text: [] for text in term_texts}

        rows = list(neo4j_session.run(_CANDIDATE_QUERY, terms=list(norm_to_originals.keys())))
        by_norm: dict[str, list[CodingCandidate]] = {}
        for row in rows:
            rec = dict(row)
            norm = rec.get("normalized")
            concept_id = rec.get("snomed_concept_id")
            if not norm or not concept_id:
                continue
            by_norm.setdefault(norm, []).append(
                CodingCandidate(
                    snomed_concept_id=str(concept_id),
                    snomed_term=rec.get("snomed_term"),
                    read_code=rec.get("read_code"),
                    score=1.0,
                    source="neo4j_hybrid",
                )
            )

        out: dict[str, list[CodingCandidate]] = {}
        for text in term_texts:
            norm = normalize_surface(text)
            out[text] = by_norm.get(norm, [])
        return out

