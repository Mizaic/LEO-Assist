"""Terminology resolution subgraph wrapping libs.terminology.client."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)


_DEFAULT_MIN_SCORE = 0.70  # matches the UI slider default


class TerminologyState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    expected_tags: dict[str, str]
    resolved_entities: list[dict[str, Any]]
    confidence_threshold: float
    errors: list[str]


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
        for e in entities:
            text = (e.get("text") or "").strip()
            if text:
                terms.append(text)
                if text not in tag_map and (
                    label := e.get("semantic_tag") or e.get("label")
                ):
                    tag_map[text] = str(label)
        results = TerminologyClient().resolve(terms, expected_tags=tag_map or None)
        resolved = [
            _merge_resolution(
                e, results.get((e.get("text") or "").strip(), []), min_score
            )
            for e in entities
        ]
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
