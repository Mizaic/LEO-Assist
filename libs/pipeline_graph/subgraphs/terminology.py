"""Terminology resolution subgraph wrapping libs.terminology.client."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.terminology.client import TerminologyClient

logger = logging.getLogger(__name__)


class TerminologyState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    expected_tags: dict[str, str]
    resolved_entities: list[dict[str, Any]]
    errors: list[str]


def _merge_resolution(e: dict[str, Any], candidates: list) -> dict[str, Any]:
    merged = dict(e)
    if not candidates:
        merged["score"] = 0.0
        return merged
    best = candidates[0]
    merged.update(
        concept_id=best.concept_id,
        term=best.term,
        semantic_tag=best.semantic_tag,
        score=best.score,
        read_code=best.read_code,
    )
    if "surface_form_status" in best.raw:
        merged["surface_form_status"] = best.raw.get("surface_form_status", "")
    return merged


def _resolve_terms(state: TerminologyState) -> dict[str, Any]:
    entities = state.get("entities") or []
    expected_tags = state.get("expected_tags") or {}
    errors: list[str] = list(state.get("errors") or [])
    if not entities:
        return {"entities": [], "resolved_entities": [], "errors": errors}
    try:
        terms = []
        tag_map: dict[str, str] = dict(expected_tags)
        for e in entities:
            text = (e.get("text") or "").strip()
            if text:
                terms.append(text)
                if text not in tag_map and (label := e.get("semantic_tag") or e.get("label")):
                    tag_map[text] = str(label)
        results = TerminologyClient().resolve(terms, expected_tags=tag_map or None)
        resolved = [
            _merge_resolution(e, results.get((e.get("text") or "").strip(), []))
            for e in entities
        ]
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
