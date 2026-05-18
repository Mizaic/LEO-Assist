"""Quality check subgraph.

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

from services.analysis_worker.app.analyzers.quality_checker import (
    run_quality_checks as run_global_quality_checks,
)

logger = logging.getLogger(__name__)


class QualityCheckState(TypedDict, total=False):
    patient_id: str
    org_id: str
    entities: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    quality_issues: list[dict[str, Any]]
    quality_report: dict[str, Any]
    errors: list[str]


def run_quality_checks(state: QualityCheckState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Running quality checks for patient %s", patient_id)
    errors = list(state.get("errors") or [])
    issues: list[dict[str, Any]] = []
    seen_texts: set[str] = set()
    for entity in state.get("entities") or []:
        text = (
            str(entity.get("text") or entity.get("surface_form") or "").strip().lower()
        )
        if text and text in seen_texts:
            issues.append(
                {
                    "episode_id": None,
                    "issue_type": "duplicate_entity",
                    "severity": "low",
                    "description": f"Duplicate entity surface form detected: {text}",
                    "suggested_action": "Review duplicate extractions",
                    "patient_id": patient_id,
                }
            )
        seen_texts.add(text)
    if not (state.get("episodes") or []):
        issues.append(
            {
                "episode_id": None,
                "issue_type": "missing_episode_context",
                "severity": "medium",
                "description": "No episodes were available for downstream review",
                "suggested_action": "Run anchor detection and episode building first",
                "patient_id": patient_id,
            }
        )
    try:
        global_report = run_global_quality_checks().to_dict()
    except Exception as exc:
        errors.append(str(exc))
        global_report = {"total_checked": 0, "compliant_count": 0, "issues": []}
    combined_issues = issues + list(global_report.get("issues") or [])
    return {
        "quality_issues": combined_issues,
        "quality_report": {
            "total_checked": max(
                len(state.get("episodes") or []), global_report.get("total_checked", 0)
            ),
            "compliant_count": max(
                max(len(state.get("episodes") or []), 0) - len(issues), 0
            ),
            "issues": combined_issues,
        },
        "errors": errors,
    }


def build_quality_check_subgraph() -> CompiledStateGraph:
    g = StateGraph(QualityCheckState)
    g.add_node("run_quality_checks", run_quality_checks)
    g.add_edge(START, "run_quality_checks")
    g.add_edge("run_quality_checks", END)
    return g.compile()
