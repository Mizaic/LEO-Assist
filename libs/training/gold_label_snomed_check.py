"""SNOMED proposal checks for gold-label and AI first-pass workflows.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

This module is runtime-safe: API services import it directly, so it must not
live under ``scripts``. It validates a proposed text/semantic-tag pair against
terminology candidates and exposes a small audit for already-coded entities.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str
    surface_text: str
    proposed_label: str
    concept_id: str | None = None
    snomed_term: str | None = None
    semantic_tag: str | None = None
    resolver_score: float = 0.0
    surface_match: float = 0.0
    tag_synonym: bool = False
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityAuditResult:
    label_id: str
    entity_index: int
    issues: tuple[str, ...]
    severity: str
    entity: dict[str, Any] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.issues


ENTITY_AUDIT_ISSUE_CODES: dict[str, str] = {
    "missing_concept_id": "Entity has a clinical label but no SNOMED concept ID.",
    "missing_snomed_term": "Entity has a SNOMED concept ID but no preferred term.",
    "missing_label": "Entity has a SNOMED concept ID but no entity label.",
    "qualifier_value_on_clinical_label": (
        "Clinical entity label points at a qualifier value concept."
    ),
    "tag_label_mismatch": "Entity label and SNOMED semantic tag do not match.",
    "stored_tag_drift": "Stored semantic_tag differs from the term suffix.",
    "blocked_assertion_with_concept": (
        "Entity has a non-present assertion while still carrying a concept."
    ),
}

_CLINICAL_LABELS = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "event",
        "body_structure",
        "morphologic_abnormality",
    }
)
_NON_CLINICAL_SEMANTIC_TAGS = frozenset(
    {
        "qualifier_value",
        "attribute",
        "staging_scale",
        "tumor_staging",
        "record_artifact",
        "geographic_location",
        "cell_structure",
        "environment",
        "occupation",
        "organism",
        "physical_object",
        "namespace_concept",
        "inactive_concept",
        "special_concept",
    }
)
_TAG_SYNONYMS: dict[str, frozenset[str]] = {
    "substance": frozenset({"medicinal_product", "product"}),
    "medicinal_product": frozenset({"substance", "product"}),
    "product": frozenset({"substance", "medicinal_product"}),
    "finding": frozenset({"disorder"}),
    "disorder": frozenset({"finding"}),
    "body_structure": frozenset({"morphologic_abnormality"}),
    "morphologic_abnormality": frozenset({"body_structure"}),
}
_BLOCKED_ASSERTIONS = frozenset(
    {
        "absent",
        "refuted",
        "declined",
        "cancelled",
        "planned",
        "hypothetical",
        "possible",
        "historical",
        "family",
    }
)
_NEGATION_WORDS = frozenset({"no", "not", "without", "absent", "negative"})
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TERM_SUFFIX_RE = re.compile(r"\(([^()]+)\)\s*$")


def _normalise_tag(tag: str | None) -> str:
    return str(tag or "").strip().lower().replace(" ", "_").replace("-", "_")


def _term_without_suffix(term: str | None) -> str:
    return _TERM_SUFFIX_RE.sub("", str(term or "")).strip()


def _term_suffix(term: str | None) -> str:
    match = _TERM_SUFFIX_RE.search(str(term or ""))
    return _normalise_tag(match.group(1)) if match else ""


def _derive_semantic_tag_from_term(term: str | None) -> str:
    return _term_suffix(term)


def _normalise_text(text: str | None) -> str:
    value = str(text or "").lower()
    return (
        value.replace("anaemia", "anemia")
        .replace("anaemic", "anemic")
        .replace("tumour", "tumor")
        .replace("litre", "liter")
    )


def _tokens(text: str | None) -> set[str]:
    return {t for t in _TOKEN_RE.findall(_normalise_text(text)) if len(t) > 1}


def surface_match_score(surface_text: str, snomed_term: str) -> float:
    """Return containment of surface tokens in the SNOMED preferred term."""
    surface = _tokens(surface_text)
    if not surface:
        return 0.0
    term = _tokens(_term_without_suffix(snomed_term))
    return len(surface & term) / len(surface)


def _candidate_value(candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        aliases = {
            "concept_id": ("concept_id", "conceptId", "snomed_concept_id"),
            "term": ("term", "preferredTerm", "snomed_term"),
            "semantic_tag": ("semantic_tag", "semanticTag"),
        }.get(key, (key,))
        for alias in aliases:
            if alias in candidate:
                return candidate.get(alias)
        return default
    return getattr(candidate, key, default)


def _tag_matches(actual: str, expected: str) -> tuple[bool, bool]:
    if not expected or not actual:
        return False, False
    if actual == expected:
        return True, False
    if actual in _TAG_SYNONYMS.get(expected, frozenset()):
        return True, True
    return False, False


def _has_negation(text: str | None) -> bool:
    return bool(_tokens(text) & _NEGATION_WORDS)


def _polarity_mismatch(surface: str, term: str) -> bool:
    return _has_negation(surface) != _has_negation(term)


def _polarity_aligned_negation(surface: str, term: str) -> bool:
    return _has_negation(surface) and _has_negation(term)


def _debug_for(candidate: Any, surface: float) -> dict[str, Any]:
    return {
        "rank1_concept_id": str(_candidate_value(candidate, "concept_id") or ""),
        "rank1_term": _term_without_suffix(str(_candidate_value(candidate, "term") or "")),
        "had_exact_match": bool(_candidate_value(candidate, "had_exact_match", False)),
        "vector_raw": float(_candidate_value(candidate, "vector_raw", 0.0) or 0.0),
        "lexical_raw": float(_candidate_value(candidate, "lexical_raw", 0.0) or 0.0),
        "surface_match": surface,
    }


def _accepted_result(
    *,
    surface_text: str,
    proposed_label: str,
    candidate: Any,
    reason: str,
    surface: float,
    tag_synonym: bool,
) -> ValidationResult:
    term = str(_candidate_value(candidate, "term") or "")
    return ValidationResult(
        accepted=True,
        reason=reason,
        surface_text=surface_text,
        proposed_label=proposed_label,
        concept_id=str(_candidate_value(candidate, "concept_id") or ""),
        snomed_term=_term_without_suffix(term),
        semantic_tag=_normalise_tag(str(_candidate_value(candidate, "semantic_tag") or "")),
        resolver_score=float(_candidate_value(candidate, "score", 0.0) or 0.0),
        surface_match=surface,
        tag_synonym=tag_synonym,
        debug=_debug_for(candidate, surface),
    )


def validate_proposal(
    surface_text: str,
    proposed_label: str,
    terminology_client: Any,
    *,
    min_resolver_score: float = 0.6,
    min_surface_match: float = 0.7,
    semantic_vector_floor: float = 0.92,
    semantic_min_surface: float = 0.66,
) -> ValidationResult:
    text = str(surface_text or "").strip()
    label = _normalise_tag(proposed_label)
    if not text or not label:
        return ValidationResult(False, "empty_input", text, label)

    resolved = terminology_client.resolve([text], expected_tags={text: label})
    candidates = list((resolved or {}).get(text, []))
    if not candidates:
        return ValidationResult(False, "no_candidates", text, label)

    first = candidates[0]
    first_surface = surface_match_score(text, str(_candidate_value(first, "term") or ""))
    first_debug = _debug_for(first, first_surface)
    saw_tag_match = False
    best: tuple[tuple[int, float, float], Any, float, bool, str] | None = None

    for candidate in candidates:
        tag = _normalise_tag(str(_candidate_value(candidate, "semantic_tag") or ""))
        tag_ok, tag_synonym = _tag_matches(tag, label)
        if not tag_ok:
            continue
        saw_tag_match = True
        term = str(_candidate_value(candidate, "term") or "")
        surface = surface_match_score(text, term)
        score = float(_candidate_value(candidate, "score", 0.0) or 0.0)
        vector = float(_candidate_value(candidate, "vector_raw", 0.0) or 0.0)
        exact = bool(_candidate_value(candidate, "had_exact_match", False))

        if _polarity_mismatch(text, term):
            return ValidationResult(
                False,
                "polarity_mismatch",
                text,
                label,
                debug=_debug_for(candidate, surface),
            )
        if exact:
            return _accepted_result(
                surface_text=text,
                proposed_label=label,
                candidate=candidate,
                reason="accepted_exact",
                surface=surface,
                tag_synonym=tag_synonym,
            )

        branch = ""
        if surface >= min_surface_match and score >= min_resolver_score:
            branch = "surface"
        elif (
            _polarity_aligned_negation(text, term)
            and surface >= semantic_min_surface
            and score >= min_resolver_score
        ):
            branch = "surface"
        elif surface >= semantic_min_surface and vector >= semantic_vector_floor:
            branch = "semantic"
        if not branch:
            continue
        rank = (
            0 if tag_synonym else 1,
            1 if branch == "semantic" else 0,
            surface,
            score,
        )
        if best is None or rank > best[0]:
            best = (rank, candidate, surface, tag_synonym, branch)

    if best is not None:
        _, candidate, surface, tag_synonym, branch = best
        suffix = "_synonym_tag" if tag_synonym else ""
        return _accepted_result(
            surface_text=text,
            proposed_label=label,
            candidate=candidate,
            reason=f"accepted_{branch}{suffix}",
            surface=surface,
            tag_synonym=tag_synonym,
        )
    if not saw_tag_match:
        return ValidationResult(False, "tag_mismatch_all", text, label, debug=first_debug)
    if float(_candidate_value(first, "score", 0.0) or 0.0) < min_resolver_score:
        reason = "low_resolver_score"
    elif first_surface < min_surface_match:
        reason = "low_surface_match"
    else:
        reason = "low_signal"
    return ValidationResult(False, reason, text, label, debug=first_debug)


def validate_proposals_batch(
    proposals: Iterable[tuple[str, str]],
    terminology_client: Any,
    **kwargs: float,
) -> dict[tuple[str, str], ValidationResult]:
    unique = {(str(text or "").strip(), _normalise_tag(label)) for text, label in proposals}
    unique = {pair for pair in unique if pair[0] or pair[1]}
    if not unique:
        return {}
    terms = sorted({text for text, _label in unique})
    expected = {text: label for text, label in unique}
    resolved = terminology_client.resolve(terms, expected_tags=expected)

    class _ResolvedClient:
        def resolve(self, terms: list[str], expected_tags: dict[str, str] | None = None):
            return {term: list((resolved or {}).get(term, [])) for term in terms}

    return {
        pair: validate_proposal(pair[0], pair[1], _ResolvedClient(), **kwargs)
        for pair in sorted(unique)
    }


def audit_existing_entity(
    entity: dict[str, Any],
    *,
    label_id: str,
    entity_index: int,
) -> EntityAuditResult:
    label = _normalise_tag(str(entity.get("label") or ""))
    stored_tag = _normalise_tag(str(entity.get("semantic_tag") or ""))
    concept_id = str(entity.get("snomed_concept_id") or "").strip()
    term = str(entity.get("snomed_term") or "").strip()
    term_tag = _term_suffix(term)
    assertion = _normalise_tag(str(entity.get("assertion") or "present"))
    issues: list[str] = []

    if not concept_id and label:
        issues.append("missing_concept_id")
    if concept_id and not label:
        issues.append("missing_label")
    if concept_id and not term:
        issues.append("missing_snomed_term")
    if concept_id and label and term_tag == "qualifier_value" and label != "qualifier_value":
        issues.append("qualifier_value_on_clinical_label")
    if concept_id and label and term_tag:
        tag_ok, _synonym = _tag_matches(term_tag, label)
        if not tag_ok and "qualifier_value_on_clinical_label" not in issues:
            issues.append("tag_label_mismatch")
    if concept_id and stored_tag and term_tag and stored_tag != term_tag:
        issues.append("stored_tag_drift")
    if concept_id and assertion in _BLOCKED_ASSERTIONS:
        issues.append("blocked_assertion_with_concept")

    if any(i in issues for i in ("missing_concept_id", "missing_label", "qualifier_value_on_clinical_label", "tag_label_mismatch")):
        severity = "critical"
    elif "missing_snomed_term" in issues:
        severity = "warning"
    elif issues:
        severity = "info"
    else:
        severity = "clean"
    return EntityAuditResult(label_id, entity_index, tuple(issues), severity, dict(entity))


def audit_gold_label_entities(
    label_id: str,
    entities_json: str | None,
) -> list[EntityAuditResult]:
    if not entities_json:
        return []
    try:
        parsed = json.loads(entities_json)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        audit_existing_entity(entity, label_id=label_id, entity_index=index)
        for index, entity in enumerate(parsed)
        if isinstance(entity, dict)
    ]
