"""Next-best-action recommendation subgraph.

Generates clinical next-best-action recommendations by evaluating the
current patient state against guidelines and the patient graph.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class NBAState(TypedDict, total=False):
    patient_id: str
    entities: list[dict[str, Any]]
    patient_context: list[dict[str, Any]]
    guidelines: list[dict[str, Any]]
    safety_net_alerts: list[dict[str, Any]]
    compliance_result: dict[str, Any]
    quality_issues: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    errors: list[str]


def generate_recommendations(state: NBAState) -> dict[str, Any]:
    """Generate next-best-action recommendations for the patient."""
    patient_id = state.get("patient_id", "unknown")
    logger.info("Generating next-best-action for patient %s", patient_id)
    recommendations: list[dict[str, Any]] = []
    if state.get("safety_net_alerts"):
        recommendations.append(
            {
                "priority": "urgent",
                "action": "Escalate safety-net alert",
                "reason": "Safety-net alerts require follow-up confirmation",
            }
        )
    compliance_result = state.get("compliance_result") or {}
    if compliance_result and not compliance_result.get("is_compliant", True):
        recommendations.append(
            {
                "priority": "high",
                "action": "Complete missing checklist items",
                "reason": "Required pathway checklist items are incomplete",
            }
        )
    if state.get("quality_issues"):
        recommendations.append(
            {
                "priority": "medium",
                "action": "Review quality issues",
                "reason": "Quality checks found data that needs clinician review",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": "routine",
                "action": "Continue pathway monitoring",
                "reason": "No blocking issues were detected in the current state",
            }
        )
    return {"recommendations": recommendations, "errors": list(state.get("errors") or [])}


def build_nba_subgraph() -> CompiledStateGraph:
    """Build and compile the next-best-action subgraph."""
    g = StateGraph(NBAState)
    g.add_node("generate_recommendations", generate_recommendations)
    g.add_edge(START, "generate_recommendations")
    g.add_edge("generate_recommendations", END)
    return g.compile()
