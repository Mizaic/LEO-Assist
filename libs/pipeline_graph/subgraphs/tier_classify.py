"""Tier classification subgraph wrapping libs.coding_engine.tier_classifier."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.coding_engine.tier_classifier import classify_tier

logger = logging.getLogger(__name__)


class TierClassifyState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    coding_mode: str
    tier_decisions: list[dict[str, Any]]


def _classify_tiers(state: TierClassifyState) -> dict[str, Any]:
    entities = state.get("entities") or []
    coding_mode = state.get("coding_mode") or "autonomous"
    decisions: list[dict[str, Any]] = []
    for i, e in enumerate(entities):
        assertion = e.get("assertion", "present")
        context_failed = bool(e.get("context_failed", False))
        terminology_score = float(e.get("score") or e.get("terminology_score", 0.0))
        surface_form_status = e.get("surface_form_status", "") or ""
        disorder_verdict = e.get("disorder_verdict", "") or ""
        td = classify_tier(
            assertion=assertion,
            context_failed=context_failed,
            terminology_score=terminology_score,
            surface_form_status=surface_form_status,
            coding_mode=coding_mode,
            disorder_verdict=disorder_verdict,
        )
        decisions.append(
            {
                "entity_index": i,
                "tier": td.tier,
                "decision": td.decision,
                "reason": td.reason,
            }
        )
    return {"tier_decisions": decisions}


def build_tier_classify_subgraph() -> CompiledStateGraph:
    graph = StateGraph(TierClassifyState)
    graph.add_node("classify_tiers", _classify_tiers)
    graph.add_edge(START, "classify_tiers")
    graph.add_edge("classify_tiers", END)
    return graph.compile()
