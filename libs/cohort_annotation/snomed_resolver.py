"""SNOMED concept resolution for cancer cohort annotation entities.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Wraps TerminologyClient.search() with label-aware scoring and tiered
auto-accept logic so we do NOT blindly take the top-1 result.

Review tiers
------------
auto_accept   Score >= 0.90 AND exact semantic-tag match AND (had_exact_match
              OR lexical_raw >= 0.90). Safe to write without human review.
needs_review  Candidates exist but confidence is below the auto-accept bar,
              or the top semantic-tag is wrong. Human picks from the shortlist.
no_match      Terminology API returned nothing for this phrase after label
              filtering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label -> SNOMED semantic-tag mapping
# ---------------------------------------------------------------------------

_LABEL_TO_SNOMED_TAG: dict[str, str] = {
    "DISORDER": "disorder",
    "FINDING": "finding",
    "PROCEDURE": "procedure",
    "OBSERVABLE_ENTITY": "observable_entity",
    "SITUATION": "situation",
    "BODY_STRUCTURE": "body_structure",
    "SUBSTANCE": "substance",
    "MEDICINAL_PRODUCT": "medicinal_product",
    "CLINICAL_DRUG": "medicinal_product",
    "QUALIFIER_VALUE": "qualifier_value",
    "REGIME_THERAPY": "regime_therapy",
    "RECORD_ARTIFACT": "record_artifact",
    # Fallback for label arrays — use primary (first) label only
}

# Auto-accept requires score >= this threshold
_AUTO_ACCEPT_SCORE: float = 0.90
# Must have at least this lexical similarity when no exact match
_AUTO_ACCEPT_LEXICAL: float = 0.90


def primary_snomed_tag(labels: list[str]) -> str | None:
    """Return the SNOMED semantic tag for the first resolvable label."""
    for lbl in labels:
        tag = _LABEL_TO_SNOMED_TAG.get(str(lbl).upper())
        if tag:
            return tag
    return None


@dataclass
class Candidate:
    concept_id: str
    preferred_term: str
    semantic_tag: str
    score: float
    had_exact_match: bool
    lexical_raw: float
    vector_raw: float
    raw: dict = field(default_factory=dict)


@dataclass
class ResolutionResult:
    quote: str
    expected_tag: str | None
    status: str  # "auto_accept" | "needs_review" | "no_match"
    chosen: Candidate | None
    candidates: list[Candidate]


def _parse_candidate(raw: dict) -> Candidate:
    return Candidate(
        concept_id=str(
            raw.get("conceptId") or raw.get("concept_id") or raw.get("snomed_concept_id") or ""
        ),
        preferred_term=str(
            raw.get("preferredTerm") or raw.get("preferred_term") or raw.get("term") or ""
        ),
        semantic_tag=str(
            raw.get("semanticTag") or raw.get("semantic_tag") or ""
        ).lower(),
        score=float(raw.get("score", 0.0)),
        had_exact_match=bool(raw.get("had_exact_match", False)),
        lexical_raw=float(raw.get("lexical_raw", 0.0)),
        vector_raw=float(raw.get("vector_raw", 0.0)),
        raw=raw,
    )


def _tag_matches(candidate: Candidate, expected_tag: str | None) -> bool:
    if not expected_tag:
        return True
    return candidate.semantic_tag == expected_tag


def _score_candidate(c: Candidate, expected_tag: str | None) -> float:
    """Compute a composite ranking score.

    Weights:
    - Base API score counts for 50%
    - Exact semantic-tag match adds 30%
    - hadExactMatch adds 20%
    This ensures a lower-scored but correctly-tagged concept beats a
    high-scored but wrongly-tagged one.
    """
    base = c.score * 0.5
    tag_bonus = 0.30 if _tag_matches(c, expected_tag) else 0.0
    exact_bonus = 0.20 if c.had_exact_match else 0.0
    return base + tag_bonus + exact_bonus


def _select_best(
    candidates: list[Candidate], expected_tag: str | None
) -> Candidate | None:
    if not candidates:
        return None
    # Keep only active concepts (concept_id non-empty)
    active = [c for c in candidates if c.concept_id]
    if not active:
        return None
    # Sort by composite score descending
    ranked = sorted(active, key=lambda c: _score_candidate(c, expected_tag), reverse=True)
    return ranked[0]


def _decide_status(
    best: Candidate | None,
    expected_tag: str | None,
    candidates: list[Candidate],
) -> str:
    if best is None:
        return "no_match"

    tag_ok = _tag_matches(best, expected_tag)
    high_score = best.score >= _AUTO_ACCEPT_SCORE
    high_lexical = best.lexical_raw >= _AUTO_ACCEPT_LEXICAL

    if tag_ok and (best.had_exact_match or high_lexical) and high_score:
        return "auto_accept"
    return "needs_review"


class SnomedResolver:
    """Batch SNOMED resolver backed by TerminologyClient."""

    def __init__(self, term_client: Any, search_limit: int = 6) -> None:
        self._client = term_client
        self._limit = search_limit

    def resolve_entity(
        self,
        quote: str,
        labels: list[str],
    ) -> ResolutionResult:
        """Resolve a single entity quote to a SNOMED concept."""
        expected_tag = primary_snomed_tag(labels)
        tags = [expected_tag] if expected_tag else None

        try:
            raw_candidates = self._client.search(
                query=quote,
                limit=self._limit,
                semantic_tags=tags,
            )
        except Exception:
            logger.warning("Terminology search failed for %r", quote[:60], exc_info=True)
            raw_candidates = []

        candidates = [_parse_candidate(r) for r in raw_candidates]

        # If the tag-filtered search returned nothing, try unfiltered
        if not candidates and expected_tag:
            try:
                raw_unfiltered = self._client.search(
                    query=quote,
                    limit=self._limit,
                )
                candidates = [_parse_candidate(r) for r in raw_unfiltered]
            except Exception:
                pass

        best = _select_best(candidates, expected_tag)
        status = _decide_status(best, expected_tag, candidates)

        return ResolutionResult(
            quote=quote,
            expected_tag=expected_tag,
            status=status,
            chosen=best,
            candidates=candidates,
        )

    def resolve_batch(
        self,
        entities: list[dict],
    ) -> list[dict]:
        """Resolve a list of aligned entities, returning enriched dicts.

        Each input entity must have at minimum:
            - "quote": str
            - "labels": list[str]

        Each output entity gains:
            - "resolution_status": "auto_accept" | "needs_review" | "no_match"
            - "snomed_concept_id": str | None
            - "snomed_term": str | None
            - "snomed_semantic_tag": str | None
            - "resolution_score": float
            - "resolution_candidates": list[dict]  (for needs_review)
        """
        results: list[dict] = []
        for ent in entities:
            quote = ent.get("quote") or ""
            labels = ent.get("labels") or []
            if not quote:
                results.append({**ent, "resolution_status": "no_match"})
                continue

            res = self.resolve_entity(quote, labels)

            enriched = dict(ent)
            enriched["resolution_status"] = res.status
            enriched["snomed_concept_id"] = res.chosen.concept_id if res.chosen else None
            enriched["snomed_term"] = res.chosen.preferred_term if res.chosen else None
            enriched["snomed_semantic_tag"] = res.chosen.semantic_tag if res.chosen else None
            enriched["resolution_score"] = res.chosen.score if res.chosen else 0.0
            enriched["expected_snomed_tag"] = res.expected_tag
            # Only carry full candidates for items needing human review
            if res.status == "needs_review":
                enriched["resolution_candidates"] = [
                    {
                        "concept_id": c.concept_id,
                        "preferred_term": c.preferred_term,
                        "semantic_tag": c.semantic_tag,
                        "score": round(c.score, 4),
                        "had_exact_match": c.had_exact_match,
                        "lexical_raw": round(c.lexical_raw, 4),
                    }
                    for c in res.candidates[:6]
                ]
            else:
                enriched["resolution_candidates"] = []

            results.append(enriched)

        return results
