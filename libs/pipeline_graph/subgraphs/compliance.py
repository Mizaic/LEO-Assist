"""Compliance evaluation subgraph.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.lab_results.pipeline import observations_from_entities

logger = logging.getLogger(__name__)


class ComplianceState(TypedDict, total=False):
    patient_id: str
    entities: list[dict[str, Any]]
    checklist: dict[str, Any]
    guideline_scope_type: str
    guideline_scope_id: str
    guideline_id: str
    patient_age: float
    patient_sex: str
    patient_observations: list[dict[str, Any]]
    guideline_result: dict[str, Any]
    compliance_result: dict[str, Any]
    compliance_report: dict[str, Any]
    errors: list[str]


def _entity_codes(entities: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for entity in entities:
        concept_id = entity.get("concept_id") or entity.get("snomed_concept_id")
        if not concept_id and isinstance(entity.get("coding"), dict):
            concept_id = entity["coding"].get("snomed_concept_id")
        code = str(concept_id or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def _evaluate_guideline(state: ComplianceState, codes: list[str]) -> dict[str, Any]:
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    scope_type = str(state.get("guideline_scope_type") or "guideline")
    scope_id = str(state.get("guideline_scope_id") or state.get("guideline_id") or "")
    observations = state.get("patient_observations")
    if observations is None:
        observations = observations_from_entities(list(state.get("entities") or []))
    result = GuidelineEvaluator().evaluate_patient(
        codes,
        pathway_filter=scope_id or None,
        patient_age=state.get("patient_age"),
        patient_sex=state.get("patient_sex"),
        scope_type=scope_type if scope_id else None,
        scope_id=scope_id or None,
        patient_observations=observations,
    )
    result["patient_code_count"] = len(codes)
    result["patient_observation_count"] = len(observations or [])
    result["is_compliant"] = bool(result.get("matched_rules"))
    return result


def evaluate_compliance(state: ComplianceState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Evaluating compliance for patient %s", patient_id)
    errors = list(state.get("errors") or [])
    entities = list(state.get("entities") or [])
    codes = _entity_codes(entities)
    if state.get("guideline_scope_id") or state.get("guideline_id"):
        try:
            result = _evaluate_guideline(state, codes)
            return {
                "compliance_result": result,
                "compliance_report": result,
                "guideline_result": result,
                "errors": errors,
            }
        except Exception as exc:
            logger.exception("Guideline evaluation failed")
            errors.append(f"guideline_evaluation: {exc}")
    checklist = state.get("checklist") or {}
    items = list(checklist.get("items") or [])
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
    summary = {
        "patient_id": patient_id,
        "items": results,
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "is_compliant": passed_count == len(results) if results else True,
    }
    return {
        "compliance_result": summary,
        "compliance_report": summary,
        "errors": errors,
    }


def build_compliance_subgraph() -> CompiledStateGraph:
    g = StateGraph(ComplianceState)
    g.add_node("evaluate_compliance", evaluate_compliance)
    g.add_edge(START, "evaluate_compliance")
    g.add_edge("evaluate_compliance", END)
    return g.compile()
