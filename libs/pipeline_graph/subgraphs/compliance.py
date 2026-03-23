"""Compliance evaluation subgraph."""

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
    errors = list(state.get("errors") or [])
    checklist = state.get("checklist") or {}
    items = list(checklist.get("items") or [])
    entities = list(state.get("entities") or [])
    entity_text = " ".join(
        str(entity.get("text") or entity.get("concept_name") or "").lower()
        for entity in entities
    )
    results: list[dict[str, Any]] = []
    for item in items:
        label = str(item.get("label") or item.get("name") or "")
        required = str(item.get("required_text") or label).lower()
        passed = bool(required and required in entity_text)
        results.append(
            {
                "label": label,
                "required": bool(item.get("required", True)),
                "passed": passed,
            }
        )
    passed_count = sum(1 for result in results if result["passed"])
    return {
        "compliance_result": {
            "patient_id": patient_id,
            "items": results,
            "passed_count": passed_count,
            "failed_count": len(results) - passed_count,
            "is_compliant": passed_count == len(results) if results else True,
        },
        "errors": errors,
    }


def build_compliance_subgraph() -> CompiledStateGraph:
    g = StateGraph(ComplianceState)
    g.add_node("evaluate_compliance", evaluate_compliance)
    g.add_edge(START, "evaluate_compliance")
    g.add_edge("evaluate_compliance", END)
    return g.compile()
