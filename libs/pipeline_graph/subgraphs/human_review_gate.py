"""Human review gate subgraph.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")

This lightweight gate is pathway-runtime compatible: it does not approve or reject
clinical content itself, but marks the run as awaiting human review when needed.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class HumanReviewGateState(TypedDict, total=False):
    coded_criteria: dict[str, Any] | None
    needs_human_review: bool
    review_status: str
    errors: list[str]


def evaluate_human_review_gate(state: HumanReviewGateState) -> dict[str, Any]:
    coded = state.get("coded_criteria")
    if not isinstance(coded, dict):
        return {"needs_human_review": True, "review_status": "pending_review"}
    needs_review = bool(coded.get("needs_human_review")) or bool(
        coded.get("hitl_terms")
    )
    return {
        "needs_human_review": needs_review,
        "review_status": "pending_review" if needs_review else "auto_ready",
    }


def build_human_review_gate_subgraph() -> CompiledStateGraph:
    g = StateGraph(HumanReviewGateState)
    g.add_node("evaluate_human_review_gate", evaluate_human_review_gate)
    g.add_edge(START, "evaluate_human_review_gate")
    g.add_edge("evaluate_human_review_gate", END)
    return g.compile()
