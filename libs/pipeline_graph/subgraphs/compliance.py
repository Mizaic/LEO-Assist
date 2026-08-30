"""Compliance evaluation subgraph.

Atlas trace:
  DO: DO-69F520C9, DO-EBD03C23, DO-C9F7BFC8
  DI: DI-F22160C3, DI-0C8DC7AB, DI-D260D249
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C9F7BFC8")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.guidelines.organ_gate import rule_requires_absent_organ
from libs.guidelines.service_rulesets import resolve_primary_guideline_ids
from libs.sbar.form_assessability import missing_referral_reason
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
    completeness_result: dict[str, Any]
    completeness_groups: list[dict[str, Any]]
    section_hits: list[dict[str, Any]]
    referral_reason: str
    form_clinical_section: str


_GUIDELINE_EXCLUDED_ASSERTIONS = frozenset(
    {"absent", "negated", "refuted", "family", "assertion_unverified"}
)
_UNSET = object()


def _entity_codes(entities: list[dict[str, Any]]) -> list[str]:
    """Return SNOMED concept IDs for present, checkable coded facts."""
    codes: list[str] = []
    for entity in entities:
        if entity.get("context_span_unresolved"):
            continue
        assertion = str(entity.get("assertion") or "").strip().lower()
        if assertion in _GUIDELINE_EXCLUDED_ASSERTIONS:
            continue
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


def _resolved_scope(
    state: ComplianceState,
    scope_type: str | None,
    scope_id: object,
    pathway_filter: object,
) -> tuple[str, str | None, str | None]:
    resolved_type = scope_type or str(state.get("guideline_scope_type") or "guideline")
    if scope_id is _UNSET:
        resolved_id = (
            str(state.get("guideline_scope_id") or state.get("guideline_id") or "")
            or None
        )
    else:
        resolved_id = str(scope_id).strip() if scope_id else None
    if pathway_filter is _UNSET:
        resolved_pathway = resolved_id
    else:
        resolved_pathway = pathway_filter if pathway_filter else None
    return resolved_type, resolved_id, resolved_pathway


def _open_knowledge_session() -> Any:
    from libs.neo4j_client.client import KnowledgeGraphClient

    try:
        return KnowledgeGraphClient().session()
    except Exception:
        return None


def _patient_eval_kwargs(
    state: ComplianceState,
    observations: list[dict[str, Any]],
    resolved_type: str,
    resolved_id: str | None,
    resolved_pathway: str | None,
) -> dict[str, Any]:
    return {
        "pathway_filter": resolved_pathway,
        "patient_age": state.get("patient_age"),
        "patient_sex": state.get("patient_sex"),
        "scope_type": (
            resolved_type if resolved_id or resolved_type == "global" else None
        ),
        "scope_id": resolved_id,
        "ruleset_version": state.get("guideline_ruleset_version") or None,
        "patient_observations": observations,
        "active_medications": list(state.get("active_medications") or []) or None,
        "allergies": list(state.get("allergies") or []) or None,
        "treatment_history": list(state.get("treatment_history") or []) or None,
    }


def _run_patient_eval(
    codes: list[str],
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    session_cm = _open_knowledge_session()
    if session_cm is None:
        return GuidelineEvaluator().evaluate_patient(codes, **kwargs), True
    with session_cm as session:
        result = GuidelineEvaluator(neo4j_session=session).evaluate_patient(
            codes, **kwargs
        )
    return result, False


def _evaluate_guideline(
    state: ComplianceState,
    codes: list[str],
    *,
    scope_type: str | None = None,
    scope_id: object = _UNSET,
    pathway_filter: object = _UNSET,
) -> dict[str, Any]:
    resolved_type, resolved_id, resolved_pathway = _resolved_scope(
        state, scope_type, scope_id, pathway_filter
    )
    observations = state.get("patient_observations")
    if observations is None:
        observations = observations_from_entities(list(state.get("entities") or []))
    kwargs = _patient_eval_kwargs(
        state, list(observations or []), resolved_type, resolved_id, resolved_pathway
    )
    result, session_failed = _run_patient_eval(codes, kwargs)
    if kwargs.get("ruleset_version"):
        result["ruleset_version"] = kwargs["ruleset_version"]
    result["patient_code_count"] = len(codes)
    result["patient_observation_count"] = len(observations or [])
    meds = list(state.get("active_medications") or [])
    result["patient_medication_count"] = len(meds)
    result["patient_allergy_count"] = len(list(state.get("allergies") or []))
    result["patient_treatment_count"] = len(list(state.get("treatment_history") or []))
    result["is_compliant"] = bool(result.get("matched_rules"))
    if session_failed:
        result["degraded"] = True
        result["session_unavailable"] = True
    return result


def _primary_guideline_ids(state: ComplianceState) -> list[str]:
    ids = [
        str(item).strip()
        for item in list(state.get("primary_guideline_ids") or [])
        if str(item).strip()
    ]
    return resolve_primary_guideline_ids(
        state.get("healthcare_service_id"),
        ids,
        ers_service_id=str(state.get("healthcare_service_ers_id") or "") or None,
    )


def _evaluate_dual_compliance(
    state: ComplianceState,
    codes: list[str],
) -> dict[str, Any]:
    primary_ids = _primary_guideline_ids(state)
    primary_rules: list[dict[str, Any]] = []
    primary_payload: dict[str, Any] = {}

    if primary_ids:
        for guideline_id in primary_ids:
            # Catalogue ids such as NG12 must use the full published
            # ruleset. The scoped compile for NG12 is a stale subset.
            payload = _evaluate_guideline(
                state,
                codes,
                scope_type="global",
                scope_id=None,
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
    alt_payload: dict[str, Any] = {}
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

    primary_rules = _drop_absent_organ_rules(primary_rules, state, codes)
    alternative_rules = _drop_absent_organ_rules(alternative_rules, state, codes)
    return _dual_result(
        state,
        primary_ids,
        primary_payload,
        primary_rules,
        alternative_rules,
        alt_payload,
    )


def _drop_absent_organ_rules(
    rules: list[dict[str, Any]],
    state: ComplianceState,
    codes: list[str],
) -> list[dict[str, Any]]:
    sex = str(state.get("patient_sex") or "")
    return [rule for rule in rules if not rule_requires_absent_organ(rule, sex, codes)]


def _dual_result(
    state: ComplianceState,
    primary_ids: list[str],
    primary_payload: dict[str, Any],
    primary_rules: list[dict[str, Any]],
    alternative_rules: list[dict[str, Any]],
    alt_payload: dict[str, Any],
) -> dict[str, Any]:
    alt_guideline_ids = sorted(
        {
            str(rule.get("guideline_id") or "").strip()
            for rule in alternative_rules
            if str(rule.get("guideline_id") or "").strip()
        }
    )
    not_compiled = bool(primary_payload.get("not_compiled"))
    degraded = bool(
        primary_payload.get("degraded") or alt_payload.get("degraded") or not_compiled
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
        "ruleset_missing": not_compiled,
    }
    result["alternatives"] = {
        "guideline_ids": alt_guideline_ids,
        "matched_rules": alternative_rules,
    }
    result["healthcare_service_missing"] = bool(state.get("healthcare_service_missing"))
    result["is_compliant"] = bool(primary_rules)
    result["degraded"] = degraded
    return result


def _guideline_evaluator() -> Any:
    from services.terminology_api.app.services.guideline_evaluator import (
        GuidelineEvaluator,
    )

    return GuidelineEvaluator()


def _missing_reason_compliance(state: ComplianceState) -> dict[str, Any]:
    """No guideline rules when there is no reason for referral to check."""
    return {
        "matched_rules": [],
        "primary": {
            "guideline_ids": list(state.get("primary_guideline_ids") or []),
            "matched_rules": [],
            "service_id": state.get("healthcare_service_id"),
            "service_name": state.get("healthcare_service_name"),
            "service_specialty": state.get("healthcare_service_specialty"),
            "supported": False,
            "ruleset_missing": False,
        },
        "alternatives": {"guideline_ids": [], "matched_rules": []},
        "healthcare_service_missing": bool(state.get("healthcare_service_missing")),
        "is_compliant": False,
        "degraded": True,
        "missing_referral_reason": True,
    }


def _completeness_for_gate(state: ComplianceState) -> dict[str, Any] | None:
    existing = state.get("completeness_result")
    if existing:
        return existing
    groups = [
        group
        for group in (state.get("completeness_groups") or [])
        if isinstance(group, dict)
    ]
    if not groups:
        return None
    from libs.completeness.evaluator import (
        concept_ids_from_entities,
        evaluate_completeness_groups,
        semantic_tags_from_entities,
    )

    entities = list(state.get("entities") or [])
    return evaluate_completeness_groups(
        groups,
        present_concept_ids=concept_ids_from_entities(entities),
        present_semantic_tags=semantic_tags_from_entities(entities),
        section_hits=list(state.get("section_hits") or []),
    )


def _ok_payload(
    state: ComplianceState,
    result: dict[str, Any],
    codes: list[str],
    entities: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
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


def evaluate_compliance(state: ComplianceState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Evaluating compliance for patient %s", patient_id)
    errors = list(state.get("errors") or [])
    entities = list(state.get("entities") or [])
    codes = _entity_codes(entities)
    if missing_referral_reason(
        referral_reason=state.get("referral_reason"),
        completeness=_completeness_for_gate(state),
        section_hits=list(state.get("section_hits") or []),
        entities=entities,
        form_clinical_section=state.get("form_clinical_section"),
    ):
        return _ok_payload(
            state, _missing_reason_compliance(state), codes, entities, errors
        )
    try:
        result = _evaluate_dual_compliance(state, codes)
        return _ok_payload(state, result, codes, entities, errors)
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
