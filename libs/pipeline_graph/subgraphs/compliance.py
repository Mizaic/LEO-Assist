"""Compliance evaluation subgraph placeholder. Wraps analysis_worker compliance logic when pipeline_worker is built."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class ComplianceState(TypedDict, total=False):
    patient_id: str
    checklist: dict[str, Any]
    compliance_report: dict[str, Any]
    errors: list[str]


def evaluate_compliance(state: ComplianceState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Evaluating compliance for patient %s", patient_id)
    return {"compliance_report": {}, "errors": list(state.get("errors") or [])}


def build_compliance_subgraph() -> CompiledStateGraph:
    g = StateGraph(ComplianceState)
    g.add_node("evaluate_compliance", evaluate_compliance)
    g.add_edge(START, "evaluate_compliance")
    g.add_edge("evaluate_compliance", END)
    return g.compile()
