"""Safety net detection subgraph placeholder. Wraps analysis_worker safety net logic when pipeline_worker is built."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class SafetyNetState(TypedDict, total=False):
    patient_id: str
    org_id: str
    episodes: list[dict[str, Any]]
    safety_net_alerts: list[dict[str, Any]]
    errors: list[str]


def detect_safety_net(state: SafetyNetState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Detecting safety net for patient %s", patient_id)
    return {"safety_net_alerts": [], "errors": list(state.get("errors") or [])}


def build_safety_net_subgraph() -> CompiledStateGraph:
    g = StateGraph(SafetyNetState)
    g.add_node("detect_safety_net", detect_safety_net)
    g.add_edge(START, "detect_safety_net")
    g.add_edge("detect_safety_net", END)
    return g.compile()
