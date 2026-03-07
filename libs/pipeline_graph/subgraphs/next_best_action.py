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
    patient_context: list[dict[str, Any]]
    guidelines: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    errors: list[str]


def generate_recommendations(state: NBAState) -> dict[str, Any]:
    """Generate next-best-action recommendations for the patient."""
    patient_id = state.get("patient_id", "unknown")
    logger.info("Generating next-best-action for patient %s", patient_id)
    return {"recommendations": [], "errors": []}


def build_nba_subgraph() -> CompiledStateGraph:
    """Build and compile the next-best-action subgraph."""
    g = StateGraph(NBAState)
    g.add_node("generate_recommendations", generate_recommendations)
    g.add_edge(START, "generate_recommendations")
    g.add_edge("generate_recommendations", END)
    return g.compile()
