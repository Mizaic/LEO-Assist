"""Anchor detection subgraph placeholder. Wraps analysis_worker anchor logic when pipeline_worker is built."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class AnchorState(TypedDict, total=False):
    patient_id: str
    org_id: str
    anchors: list[dict[str, Any]]
    errors: list[str]


def detect_anchors(state: AnchorState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Detecting anchors for patient %s", patient_id)
    return {"anchors": [], "errors": list(state.get("errors") or [])}


def build_anchor_subgraph() -> CompiledStateGraph:
    g = StateGraph(AnchorState)
    g.add_node("detect_anchors", detect_anchors)
    g.add_edge(START, "detect_anchors")
    g.add_edge("detect_anchors", END)
    return g.compile()
