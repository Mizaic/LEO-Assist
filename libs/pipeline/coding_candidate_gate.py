"""Keep and cheap-filter the SNOMED shortlist before the coding verifier.

Atlas trace:
  DI: DI-0EC8620E
  DO: DO-8121F927
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8121F927")

Terminology returns a ranked list. The worker used to keep only the first
hit. This module keeps the top safe candidates and drops pairs that the
blocklist or a semantic-tag family mismatch already rules out.
"""

from __future__ import annotations

from typing import Any, Callable

from libs.terminology.semantic_tag import normalise_semantic_tag

SHORTLIST_SIZE = 5

_CLINICAL = frozenset(
    {
        "finding",
        "disorder",
        "situation",
        "event",
        "morphologic_abnormality",
    }
)
_OBSERVABLE = frozenset(
    {
        "observable_entity",
        "assessment_scale",
        "staging_scale",
        "qualifier_value",
        "tumor_staging",
    }
)
_PROCEDURE = frozenset({"procedure", "regime_therapy"})
_SUBSTANCE = frozenset(
    {
        "substance",
        "medicinal_product",
        "clinical_drug",
        "product",
        "physical_object",
    }
)
_ANATOMY = frozenset({"body_structure"})
_ORGANISM = frozenset({"organism"})
_FAMILY_SETS = (
    ("clinical", _CLINICAL),
    ("observable", _OBSERVABLE),
    ("procedure", _PROCEDURE),
    ("substance", _SUBSTANCE),
    ("anatomy", _ANATOMY),
    ("organism", _ORGANISM),
)
_COMPATIBLE_PAIRS = frozenset(
    {
        frozenset({"clinical", "observable"}),
        frozenset({"procedure", "observable"}),
    }
)

IsBlocked = Callable[[str, str | None], bool]


def _tag_family(tag: str | None) -> str:
    normalised = normalise_semantic_tag(tag)
    for name, members in _FAMILY_SETS:
        if normalised in members:
            return name
    return normalised or "unknown"


def tags_compatible(expected: str | None, candidate: str | None) -> bool:
    """Return True when the candidate tag can stand for the extracted span."""
    if not expected or not candidate:
        return True
    expected_family = _tag_family(expected)
    candidate_family = _tag_family(candidate)
    if expected_family == candidate_family:
        return True
    return frozenset({expected_family, candidate_family}) in _COMPATIBLE_PAIRS


def candidate_as_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return {
            "concept_id": str(candidate.get("concept_id") or "") or None,
            "term": candidate.get("term"),
            "semantic_tag": candidate.get("semantic_tag"),
            "score": float(candidate.get("score") or 0.0),
            "read_code": candidate.get("read_code"),
            "had_exact_match": bool(candidate.get("had_exact_match")),
        }
    return {
        "concept_id": str(getattr(candidate, "concept_id", None) or "") or None,
        "term": getattr(candidate, "term", None),
        "semantic_tag": getattr(candidate, "semantic_tag", None),
        "score": float(getattr(candidate, "score", 0.0) or 0.0),
        "read_code": getattr(candidate, "read_code", None),
        "had_exact_match": bool(getattr(candidate, "had_exact_match", False)),
    }


def _expected_tag(entity: dict[str, Any]) -> str | None:
    return str(entity.get("semantic_tag") or entity.get("label") or "").strip() or None


def filter_coding_candidates(
    entity: dict[str, Any],
    candidates: list[Any],
    *,
    is_blocked: IsBlocked,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Drop blocked and cross-family candidates. Keep at most five."""
    text = str(entity.get("text") or "")
    expected = _expected_tag(entity)
    kept: list[dict[str, Any]] = []
    for raw in candidates:
        item = candidate_as_dict(raw)
        concept_id = item.get("concept_id")
        if not concept_id:
            continue
        if float(item.get("score") or 0.0) < min_score:
            continue
        if is_blocked(text, str(concept_id)):
            continue
        if not tags_compatible(expected, item.get("semantic_tag")):
            continue
        kept.append(item)
        if len(kept) >= SHORTLIST_SIZE:
            break
    return kept


def apply_draft_from_shortlist(
    entity: dict[str, Any],
    shortlist: list[dict[str, Any]],
) -> dict[str, Any]:
    """Stamp the first remaining candidate as the draft code."""
    merged = dict(entity)
    merged["coding_candidates"] = shortlist
    if not shortlist:
        merged["terminology_unresolved"] = True
        merged["score"] = float(merged.get("score") or 0.0)
        for field in ("concept_id", "term", "read_code"):
            merged[field] = None
        return merged
    best = shortlist[0]
    merged.update(
        concept_id=best.get("concept_id"),
        term=best.get("term"),
        semantic_tag=best.get("semantic_tag") or merged.get("semantic_tag"),
        score=round(float(best.get("score") or 0.0), 4),
        read_code=best.get("read_code"),
        terminology_unresolved=False,
        had_exact_match=bool(best.get("had_exact_match")),
    )
    return merged
