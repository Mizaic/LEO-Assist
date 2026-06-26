"""Quality check subgraph.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.completeness.evaluator import (
    build_isa_expansion,
    concept_ids_from_entities,
    evaluate_completeness_groups,
    semantic_tags_from_entities,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from services.analysis_worker.app.analyzers.quality_checker import (
    run_quality_checks as run_global_quality_checks,
)

logger = logging.getLogger(__name__)


class QualityCheckState(TypedDict, total=False):
    patient_id: str
    org_id: str
    entities: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    completeness_domain: str
    completeness_subdomain: str
    completeness_result: dict[str, Any]
    quality_issues: list[dict[str, Any]]
    quality_report: dict[str, Any]
    errors: list[str]


def _valueset_id(subdomain: str) -> str:
    return f"ncda-{subdomain.replace('_', '-')}"


def _coerce_schema(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    parsed = json.loads(value) if isinstance(value, str) else value
    if isinstance(parsed, dict):
        parsed = parsed.get("groups") or []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _load_completeness_schema(domain: str, subdomain: str) -> list[dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (d:AuditDomain {id: $domain})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
            "WHERE v.id = $vs_id OR v.name = $subdomain "
            "RETURN v.completeness_schema AS completeness_schema",
            domain=domain,
            subdomain=subdomain,
            vs_id=_valueset_id(subdomain),
        )
    finally:
        client.close()
    return _coerce_schema((rows or [{}])[0].get("completeness_schema"))


def _all_required_concept_ids(schema: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for group in schema:
        for cid in group.get("concept_ids", []):
            try:
                parsed = int(cid)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                ids.add(parsed)
    return ids


def _load_isa_expansion(required_ids: set[int]) -> dict[int, set[int]]:
    if not required_ids:
        return {}
    client = KnowledgeGraphClient()
    try:
        return build_isa_expansion(required_ids, client.run)
    finally:
        client.close()


def _run_completeness_check(state: QualityCheckState) -> dict[str, Any] | None:
    domain = str(state.get("completeness_domain") or "").strip()
    subdomain = str(state.get("completeness_subdomain") or "").strip()
    if not domain or not subdomain:
        return None
    schema = _load_completeness_schema(domain, subdomain)
    if not schema:
        return {
            "domain": domain,
            "subdomain": subdomain,
            "configured": False,
            "complete": False,
            "matched_groups": [],
            "missing_groups": [],
        }
    entities = list(state.get("entities") or [])
    required_ids = _all_required_concept_ids(schema)
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids=concept_ids_from_entities(entities),
        present_semantic_tags=semantic_tags_from_entities(entities),
        isa_expansion=_load_isa_expansion(required_ids),
    )
    return {**result, "domain": domain, "subdomain": subdomain, "configured": True}


def _duplicate_entity_issues(
    entities: list[dict[str, Any]], patient_id: str
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    for entity in entities:
        text = (
            str(entity.get("text") or entity.get("surface_form") or "").strip().lower()
        )
        if not text:
            continue
        if text in seen_texts:
            issues.append(_quality_issue("duplicate_entity", "low", patient_id, text))
        seen_texts.add(text)
    return issues


def _quality_issue(
    issue_type: str, severity: str, patient_id: str, detail: str = ""
) -> dict[str, Any]:
    descriptions = {
        "duplicate_entity": f"Duplicate entity surface form detected: {detail}",
        "missing_episode_context": "No episodes were available for downstream review",
        "minimum_dataset_incomplete": "Required referral information is missing",
    }
    actions = {
        "duplicate_entity": "Review duplicate extractions",
        "missing_episode_context": "Run anchor detection and episode building first",
        "minimum_dataset_incomplete": "Review the minimum dataset fields",
    }
    return {
        "episode_id": None,
        "issue_type": issue_type,
        "severity": severity,
        "description": descriptions[issue_type],
        "suggested_action": actions[issue_type],
        "patient_id": patient_id,
    }


def _global_quality_report(errors: list[str]) -> dict[str, Any]:
    try:
        return run_global_quality_checks().to_dict()
    except Exception as exc:
        errors.append(str(exc))
        return {"total_checked": 0, "compliant_count": 0, "issues": []}


def run_quality_checks(state: QualityCheckState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Running quality checks for patient %s", patient_id)
    errors = list(state.get("errors") or [])
    entities = list(state.get("entities") or [])
    episodes = list(state.get("episodes") or [])
    issues = _duplicate_entity_issues(entities, patient_id)
    if not episodes:
        issues.append(_quality_issue("missing_episode_context", "medium", patient_id))
    global_report = _global_quality_report(errors)
    completeness = _run_completeness_check(state)
    if completeness and not completeness.get("complete"):
        issues.append(
            _quality_issue("minimum_dataset_incomplete", "medium", patient_id)
        )
    combined_issues = issues + list(global_report.get("issues") or [])
    result: dict[str, Any] = {
        "quality_issues": combined_issues,
        "quality_report": {
            "total_checked": max(len(episodes), global_report.get("total_checked", 0)),
            "compliant_count": max(max(len(episodes), 0) - len(issues), 0),
            "issues": combined_issues,
        },
        "errors": errors,
    }
    if completeness:
        result["completeness_result"] = completeness
        result["quality_report"]["completeness"] = completeness
    return result


def build_quality_check_subgraph() -> CompiledStateGraph:
    g = StateGraph(QualityCheckState)
    g.add_node("run_quality_checks", run_quality_checks)
    g.add_edge(START, "run_quality_checks")
    g.add_edge("run_quality_checks", END)
    return g.compile()
