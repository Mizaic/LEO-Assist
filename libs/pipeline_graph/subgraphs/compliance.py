"""Compliance evaluation subgraph.

Atlas trace:
  DO: DO-69F520C9, DO-EBD03C23
  DI: DI-F22160C3, DI-0C8DC7AB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.lab_results.pipeline import observations_from_entities
from libs.pipeline_graph.subgraphs.compliance_diagnostics import (
    build_guideline_diagnostics,
    build_stage_summary,
)

logger = logging.getLogger(__name__)


class ComplianceState(TypedDict, total=False):
    patient_id: str
    entities: list[dict[str, Any]]
    checklist: dict[str, Any]
    guideline_scope_type: str
    guideline_scope_id: str
    guideline_id: str
    primary_guideline_ids: list[str]
    healthcare_service_id: str
    healthcare_service_name: str
    healthcare_service_specialty: str
    healthcare_service_spoa_id: str
    healthcare_service_missing: bool
    guideline_ruleset_version: str
    patient_age: float
    patient_sex: str
    patient_observations: list[dict[str, Any]]
    guideline_result: dict[str, Any]
    compliance_result: dict[str, Any]
    compliance_report: dict[str, Any]
    stage_summary: dict[str, Any]
    guideline_diagnostics: dict[str, Any]
    errors: list[str]


def _entity_codes(entities: list[dict[str, Any]]) -> list[str]:
    """Return SNOMED concept IDs for all coded entities in a pipeline run."""
    codes: list[str] = []
    for entity in entities:
        concept_id = entity.get("concept_id") or entity.get("snomed_concept_id")
        if not concept_id and isinstance(entity.get("coding"), dict):
            concept_id = entity["coding"].get("snomed_concept_id")
        code = str(concept_id or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def _dedupe_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "").strip()
        if not rule_id or rule_id in merged:
            continue
        merged[rule_id] = rule
    return list(merged.values())


def _evaluate_guideline(
    state: ComplianceState,
    codes: list[str],
    *,
    scope_type: str | None = None,
    scope_id: str | None = None,
    pathway_filter: str | None = None,
) -> dict[str, Any]:
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    resolved_scope_type = scope_type or str(
        state.get("guideline_scope_type") or "guideline"
    )
    resolved_scope_id = scope_id or str(
        state.get("guideline_scope_id") or state.get("guideline_id") or ""
    )
    resolved_pathway = (
        pathway_filter if pathway_filter is not None else (resolved_scope_id or None)
    )
    observations = state.get("patient_observations")
    if observations is None:
        observations = observations_from_entities(list(state.get("entities") or []))
    active_medications = list(state.get("active_medications") or [])
    allergies = list(state.get("allergies") or [])
    treatment_history = list(state.get("treatment_history") or [])
    ruleset_version = state.get("guideline_ruleset_version") or None
    result = GuidelineEvaluator().evaluate_patient(
        codes,
        pathway_filter=resolved_pathway,
        patient_age=state.get("patient_age"),
        patient_sex=state.get("patient_sex"),
        scope_type=resolved_scope_type if resolved_scope_id else None,
        scope_id=resolved_scope_id or None,
        ruleset_version=ruleset_version,
        patient_observations=observations,
        active_medications=active_medications or None,
        allergies=allergies or None,
        treatment_history=treatment_history or None,
    )
    if ruleset_version:
        result["ruleset_version"] = ruleset_version
    result["patient_code_count"] = len(codes)
    result["patient_observation_count"] = len(observations or [])
    result["patient_medication_count"] = len(active_medications)
    result["patient_allergy_count"] = len(allergies)
    result["patient_treatment_count"] = len(treatment_history)
    result["is_compliant"] = bool(result.get("matched_rules"))
    return result


def _primary_guideline_ids(state: ComplianceState) -> list[str]:
    ids = [
        str(item).strip()
        for item in list(state.get("primary_guideline_ids") or [])
        if str(item).strip()
    ]
    if ids:
        return ids
    scope_id = str(state.get("guideline_scope_id") or state.get("guideline_id") or "")
    return [scope_id] if scope_id else []


def _evaluate_dual_compliance(
    state: ComplianceState,
    codes: list[str],
) -> dict[str, Any]:
    primary_ids = _primary_guideline_ids(state)
    primary_rules: list[dict[str, Any]] = []
    primary_payload: dict[str, Any] = {}

    if primary_ids:
        for guideline_id in primary_ids:
            payload = _evaluate_guideline(
                state,
                codes,
                scope_type="guideline",
                scope_id=guideline_id,
                pathway_filter=guideline_id,
            )
            primary_payload = payload
            primary_rules.extend(payload.get("matched_rules") or [])
        primary_rules = _dedupe_rules(primary_rules)
    else:
        primary_payload = _evaluate_guideline(
            state,
            codes,
            scope_type="global",
            scope_id=None,
            pathway_filter=None,
        )
        primary_rules = list(primary_payload.get("matched_rules") or [])

    alternative_rules: list[dict[str, Any]] = []
    if not primary_rules:
        alt_payload = _evaluate_guideline(
            state,
            codes,
            scope_type="global",
            scope_id=None,
            pathway_filter=None,
        )
        primary_set = set(primary_ids)
        for rule in alt_payload.get("matched_rules") or []:
            guideline_id = str(rule.get("guideline_id") or "").strip()
            if guideline_id and guideline_id in primary_set:
                continue
            alternative_rules.append(rule)
        alternative_rules = _dedupe_rules(alternative_rules)

    alt_guideline_ids = sorted(
        {
            str(rule.get("guideline_id") or "").strip()
            for rule in alternative_rules
            if str(rule.get("guideline_id") or "").strip()
        }
    )

    result = dict(primary_payload or {})
    result["matched_rules"] = primary_rules
    result["primary"] = {
        "guideline_ids": primary_ids,
        "matched_rules": primary_rules,
        "service_id": state.get("healthcare_service_id"),
        "service_name": state.get("healthcare_service_name"),
        "service_specialty": state.get("healthcare_service_specialty"),
        "supported": bool(primary_rules),
    }
    result["alternatives"] = {
        "guideline_ids": alt_guideline_ids,
        "matched_rules": alternative_rules,
    }
    result["healthcare_service_missing"] = bool(state.get("healthcare_service_missing"))
    result["is_compliant"] = bool(primary_rules)
    return result


def _guideline_evaluator() -> Any:
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    return GuidelineEvaluator()


def evaluate_compliance(state: ComplianceState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Evaluating compliance for patient %s", patient_id)
    errors = list(state.get("errors") or [])
    entities = list(state.get("entities") or [])
    codes = _entity_codes(entities)
    try:
        result = _evaluate_dual_compliance(state, codes)
        payload = {
            "compliance_result": result,
            "compliance_report": result,
            "guideline_result": result,
            "stage_summary": build_stage_summary(
                state, codes=codes, entities=entities, result=result
            ),
            "errors": errors,
        }
        if state.get("capture_validation_output"):
            payload["guideline_diagnostics"] = build_guideline_diagnostics(
                _guideline_evaluator(),
                state,
                codes=codes,
                result=result,
            )
        return payload
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
