"""Quality check subgraph placeholder. Wraps analysis_worker quality logic when pipeline_worker is built."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class QualityCheckState(TypedDict, total=False):
    patient_id: str
    org_id: str
    episodes: list[dict[str, Any]]
    quality_issues: list[dict[str, Any]]
    errors: list[str]


def run_quality_checks(state: QualityCheckState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Running quality checks for patient %s", patient_id)
    return {"quality_issues": [], "errors": list(state.get("errors") or [])}


def build_quality_check_subgraph() -> CompiledStateGraph:
    g = StateGraph(QualityCheckState)
    g.add_node("run_quality_checks", run_quality_checks)
    g.add_edge(START, "run_quality_checks")
    g.add_edge("run_quality_checks", END)
    return g.compile()
