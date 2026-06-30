"""Terminology resolution subgraph wrapping libs.terminology.client.

Atlas trace:
  DO: DO-16FFE9D3
  Also implements: DO-36C09C0E, DO-8620A68B
  DI: DI-04105500, DI-4247C7E5, DI-5A802C83
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-16FFE9D3")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.pipeline.post_processing import (
    fix_double_negated_situations,
    fix_polarity_encoded_findings,
)
from libs.lab_results.pipeline import enrich_lab_result_findings
from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)


# Minimum calibrated absolute confidence to accept a SNOMED mapping.
# Calibrated ~ P(correct mapping). 0.55 admits:
#   - Exact-branch hits (lex_signal=1.0 -> calibrated=1.0)
#   - Strong fulltext (BM25>=2) with tag match (~0.67+0.10=0.77)
#   - High-cosine vector hits (>=0.85)
# Rejects:
#   - Weak partial Lucene matches whose only candidate was a one-token
#     hit (calibrated <= 0.5).
# Was 0.70 under the old per-term-normalised scoring; lowered to 0.55
# now that the score reflects absolute strength rather than relative
# rank within the per-term candidate pool.
_DEFAULT_MIN_SCORE = 0.55
_TERM_CONCEPT_BLOCKLIST: dict[str, set[str]] = {
    # Generic mention in notes; do not auto-code to a specific named operation.
    "spinal surgery": {"1287097003"},
    # Symptom phrasing should not be coerced to broad malaise.
    "not sleeping well": {"367391008"},
    # Mechanical wording in patient advice; not malignant neoplasm of nervous system.
    "nerve compression": {"372063002"},
    # FIT is a test (Faecal Immunochemical Test), not a seizure.
    "fit": {"91175000"},
}


def _normalise_text_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _is_blocked_mapping(text: str, concept_id: str | None) -> bool:
    if not concept_id:
        return False
    blocked = _TERM_CONCEPT_BLOCKLIST.get(_normalise_text_key(text))
    return bool(blocked and str(concept_id) in blocked)


class TerminologyState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    expected_tags: dict[str, str]
    resolved_entities: list[dict[str, Any]]
    confidence_threshold: float
    patient_age: float
    patient_sex: str
    errors: list[str]


# Leading tokens that are never useful as the core SNOMED lookup term.
# Stripping them increases the chance of an exact-branch hit.
_LOOKUP_STRIP_PREFIXES = frozenset(
    {
        "moderate",
        "mild",
        "severe",
        "marked",
        "significant",
        "bilateral",
        "left",
        "right",
        "small",
        "large",
        "central",
        "peripheral",
        "anterior",
        "posterior",
        "medial",
        "lateral",
        "proximal",
        "distal",
        "diffuse",
        "focal",
        "generalised",
        "generalized",
        "extensive",
        "complex",
        "simple",
        "high-risk",
        "high risk",
        "low-risk",
        "low risk",
    }
)


def _strip_leading_modifiers(text: str) -> str:
    """Remove leading qualifier words that hurt SNOMED lexical matching.

    Drops one leading token at a time (case-insensitive) while the first
    word is a known non-clinical modifier.  Stops as soon as the first
    word is clinical so we never strip the concept itself.
    """
    words = text.split()
    while words and words[0].lower().rstrip("-,;") in _LOOKUP_STRIP_PREFIXES:
        words = words[1:]
    return " ".join(words) if words else text


def _resolve_lookup_term(entity: dict[str, Any]) -> str:
    lookup = str(entity.get("lookup_term") or "").strip()
    text = str(entity.get("text") or "").strip()

    # When the LLM sets lookup_term to the same value as text (or leaves it
    # empty), strip leading qualifier/laterality tokens so the SNOMED
    # resolver sees "ovary enlarged" instead of "left ovary enlarged" and
    # "ascites" instead of "moderate ascites".
    if not lookup or lookup.lower() == text.lower():
        stripped = _strip_leading_modifiers(text)
        if stripped and stripped != text:
            return stripped
        if not lookup:
            # Fall through to relation-based enrichment below.
            pass
        else:
            return lookup

    if lookup:
        return lookup

    relations = list(entity.get("__relations") or [])
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        if str(rel.get("type") or "").strip().lower() != "finding_site":
            continue
        tail = str(rel.get("target_text") or "").strip()
        if tail and text:
            return f"{tail} {text}".strip()
    return text


def _merge_resolution(
    e: dict[str, Any],
    candidates: list,
    min_score: float = _DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    merged = dict(e)
    if not candidates:
        merged["score"] = 0.0
        merged["terminology_unresolved"] = True
        return merged
    best = candidates[0]
    if _is_blocked_mapping(str(e.get("text") or ""), best.concept_id):
        merged["score"] = round(float(best.score or 0.0), 4)
        merged["terminology_unresolved"] = True
        for field in ("concept_id", "term", "read_code"):
            merged[field] = None
        logger.info(
            "Terminology: blocked unsafe mapping %r -> %s (%r)",
            e.get("text"),
            best.concept_id,
            best.term,
        )
        return merged
    if best.score < min_score:
        # Score too low — keep the entity but do not apply a code.
        # Downstream steps (surface form validation, persist) must not trust
        # an unreliable SNOMED match, so we clear the code fields entirely.
        merged["score"] = round(best.score, 4)
        merged["terminology_unresolved"] = True
        # Preserve any existing code fields as None so callers can tell they
        # were checked but rejected, rather than never attempted.
        for field in ("concept_id", "term", "read_code"):
            merged[field] = None
        logger.info(
            "Terminology: rejected %r → %r (score %.4f < threshold %.2f)",
            e.get("text"),
            best.term,
            best.score,
            min_score,
        )
        return merged
    merged.update(
        concept_id=best.concept_id,
        term=best.term,
        semantic_tag=best.semantic_tag,
        score=round(best.score, 4),
        read_code=best.read_code,
        terminology_unresolved=False,
    )
    if "surface_form_status" in best.raw:
        merged["surface_form_status"] = best.raw.get("surface_form_status", "")
    return merged


def _dedup_by_concept_id(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate resolved entities that share a concept_id.

    Multi-classification produces distinct (surface_form, entity_type) pairs
    that should resolve to different concepts.  Any that collide -- same
    concept_id returned for different entity types -- are deduplicated by
    keeping the highest-scoring candidate so the graph MERGE produces one
    :DOCUMENTS link rather than a phantom duplicate.

    Unresolved entities (terminology_unresolved=True or no concept_id) are
    always kept regardless.
    """
    seen: dict[str, dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    for ent in entities:
        concept_id = str(ent.get("concept_id") or "").strip()
        if not concept_id or ent.get("terminology_unresolved"):
            kept.append(ent)
            continue
        existing = seen.get(concept_id)
        if existing is None:
            seen[concept_id] = ent
            kept.append(ent)
        elif float(ent.get("score") or 0) > float(existing.get("score") or 0):
            kept.remove(existing)
            seen[concept_id] = ent
            kept.append(ent)
    return kept


def _resolve_terms(state: TerminologyState) -> dict[str, Any]:
    entities = state.get("entities") or []
    expected_tags = state.get("expected_tags") or {}
    errors: list[str] = list(state.get("errors") or [])
    min_score = float(state.get("confidence_threshold") or _DEFAULT_MIN_SCORE)
    if not entities:
        return {"entities": [], "resolved_entities": [], "errors": errors}
    try:
        terms = []
        tag_map: dict[str, str] = dict(expected_tags)
        lookup_by_index: dict[int, str] = {}
        for e in entities:
            idx = len(lookup_by_index)
            lookup = _resolve_lookup_term(e)
            lookup_by_index[idx] = lookup
            if lookup:
                terms.append(lookup)
                if lookup not in tag_map and (
                    label := e.get("semantic_tag") or e.get("label")
                ):
                    tag_map[lookup] = str(label)
        results = TerminologyClient().resolve(terms, expected_tags=tag_map or None)
        resolved = []
        for idx, entity in enumerate(entities):
            lookup = lookup_by_index.get(idx) or ""
            merged = _merge_resolution(entity, results.get(lookup, []), min_score)
            if lookup:
                merged["lookup_term"] = lookup
            resolved.append(merged)
        unresolved = [r for r in resolved if r.get("terminology_unresolved")]
        if unresolved:
            errors.append(
                f"terminology_low_confidence: {len(unresolved)} entity/entities below "
                f"score threshold {min_score:.2f} — "
                + ", ".join(
                    f'"{u.get("text")}" (score {u.get("score", 0):.2f})'
                    for u in unresolved
                )
            )
        fix_double_negated_situations(resolved)
        fix_polarity_encoded_findings(resolved)
        resolved = enrich_lab_result_findings(
            resolved,
            patient_sex=state.get("patient_sex"),
            patient_age=state.get("patient_age"),
        )
        resolved = _dedup_by_concept_id(resolved)
        return {"entities": resolved, "resolved_entities": resolved, "errors": errors}
    except Exception as exc:
        logger.exception("Terminology resolution failed")
        errors.append(f"terminology: {exc}")
        return {"entities": entities, "resolved_entities": entities, "errors": errors}


def build_terminology_subgraph() -> CompiledStateGraph:
    graph = StateGraph(TerminologyState)
    graph.add_node("resolve_terms", _resolve_terms)
    graph.add_edge(START, "resolve_terms")
    graph.add_edge("resolve_terms", END)
    return graph.compile()
