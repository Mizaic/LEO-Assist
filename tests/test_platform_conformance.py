"""U4.7 -- platform conformance suite parameterized over workflow versions."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

import libs.pipeline_graph.capability_registry as capability_registry_mod
from libs.pipeline_graph.capability_registry import (
    get_capability_registry,
    validate_plan_snapshot,
)
from libs.workflow.validation_workflows import all_validation_plan_definitions


@pytest.fixture(scope="module")
def capability_registry():
    """Rebuild registry after pytest imports so subgraphs are registered."""
    capability_registry_mod._default_capability_registry = None
    return get_capability_registry()


def _load_seed_module():
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    scripts_dir = os.path.join(repo_root, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "seed_plan_definitions",
        os.path.join(scripts_dir, "seed_plan_definitions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _all_conformance_plans() -> list[dict]:
    mod = _load_seed_module()
    seen: set[str] = set()
    plans: list[dict] = []
    for plan in [*mod.PLAN_DEFINITIONS, *all_validation_plan_definitions()]:
        plan_id = str(plan.get("id") or "")
        if not plan_id or plan_id in seen:
            continue
        seen.add(plan_id)
        plans.append(plan)
    return plans


def _plan_ids() -> list[str]:
    return [str(p["id"]) for p in _all_conformance_plans()]


def _plan_by_id(plan_id: str) -> dict:
    for plan in _all_conformance_plans():
        if plan.get("id") == plan_id:
            return plan
    raise KeyError(plan_id)


def _walk_subgraph_chain(actions: list[dict]) -> list[str]:
    by_id = {a["id"]: a for a in actions}
    successor: dict[str, str] = {}
    for action in actions:
        for rel in action.get("relatedAction") or []:
            predecessor = rel.get("actionId")
            if predecessor:
                successor[predecessor] = action["id"]
    trigger = next(
        (a for a in actions if a.get("trigger") or a.get("_nodeType") == "trigger"),
        min(actions, key=lambda x: x.get("_sequence", 999)),
    )
    ordered: list[str] = []
    current_id = trigger["id"]
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        action = by_id[current_id]
        subgraph_id = str(action.get("_subgraphId") or "")
        if subgraph_id not in {"trigger", ""}:
            ordered.append(subgraph_id)
        current_id = successor.get(current_id)
    return ordered


_PLACEHOLDER_SUBGRAPHS = {"durable_step", "durable_referral_workflow", ""}


@pytest.mark.parametrize("plan_id", _plan_ids())
def test_plan_snapshot_passes_capability_validation(
    plan_id: str, capability_registry
) -> None:
    plan = _plan_by_id(plan_id)
    errors = validate_plan_snapshot(plan, registry=capability_registry)
    assert errors == [], f"{plan_id} validation errors: {errors}"


@pytest.mark.parametrize("plan_id", _plan_ids())
def test_plan_actions_have_registered_subgraph_ids(
    plan_id: str, capability_registry
) -> None:
    plan = _plan_by_id(plan_id)
    reg = capability_registry
    for action in plan.get("action") or []:
        node_type = action.get("_nodeType") or ""
        if node_type == "trigger" or action.get("trigger"):
            continue
        cap_id = str(action.get("_subgraphId") or node_type or "")
        if not cap_id:
            continue
        assert reg.has(
            cap_id
        ), f"{plan_id} action {action.get('id')} uses unregistered capability {cap_id}"


@pytest.mark.parametrize(
    "plan_id",
    [
        p
        for p in _plan_ids()
        if p
        in {
            "pd-referral-assessment",
            "pd-gp-encounter-coding",
            "pd-gold-training-audit",
            "pd-episode-bundle-coding",
            "pd-val-key-fact-extraction",
            "pd-val-pathway-criteria",
            "pd-val-triage-completeness",
            "pd-val-terminology-mapping",
            "pd-val-sbar-summary",
            "pd-referral-triage-e2e",
        }
    ],
)
def test_durable_plans_declare_pubsub_workflow_mode(plan_id: str) -> None:
    plan = _plan_by_id(plan_id)
    assert plan.get("_workflowMode") == "durable_pubsub"


def test_referral_plan_has_eleven_step_clinical_chain() -> None:
    plan = _plan_by_id("pd-referral-assessment")
    chain = _walk_subgraph_chain(plan["action"])
    expected = [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "coding_verifier",
        "snomed_enrichment",
        "relation_linking",
        "persist",
        "referral_reason",
        "compliance",
        "quality_check",
        "sbar",
    ]
    assert chain == expected


@pytest.mark.parametrize("plan_id", _plan_ids())
def test_plan_has_no_placeholder_subgraph_ids(plan_id: str) -> None:
    plan = _plan_by_id(plan_id)
    for action in plan.get("action") or []:
        subgraph_id = str(action.get("_subgraphId") or "")
        node_type = action.get("_nodeType") or ""
        if node_type == "trigger" or action.get("trigger"):
            continue
        assert (
            subgraph_id not in _PLACEHOLDER_SUBGRAPHS
        ), f"{plan_id} action {action.get('id')} uses placeholder {subgraph_id!r}"


@pytest.mark.parametrize("plan_id", _plan_ids())
def test_plan_actions_have_non_negative_sequence(plan_id: str) -> None:
    plan = _plan_by_id(plan_id)
    for action in plan.get("action") or []:
        if action.get("_sequence") is None:
            continue
        assert int(action["_sequence"]) >= 0
