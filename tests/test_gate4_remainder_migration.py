"""Gate 4 remainder -- durable_pubsub migration for training, validation, episode."""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from libs.workflow.durable_step_runner import is_durable_runner_enabled
from libs.workflow.validation_workflows import (
    VALIDATION_PLAN_DEFINITIONS,
    REFERRAL_TRIAGE_PLAN_DEFINITION,
    all_validation_plan_definitions,
)

_GATE4_DURABLE_PLAN_IDS = (
    "pd-gold-training-audit",
    "pd-episode-bundle-coding",
    "pd-val-key-fact-extraction",
    "pd-val-pathway-criteria",
    "pd-val-triage-completeness",
    "pd-val-terminology-mapping",
    "pd-val-sbar-summary",
    "pd-referral-triage-e2e",
)


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


def _plan_by_id(plan_id: str) -> dict:
    mod = _load_seed_module()
    for plan in mod.PLAN_DEFINITIONS:
        if plan.get("id") == plan_id:
            return plan
    for plan in all_validation_plan_definitions():
        if plan.get("id") == plan_id:
            return plan
    raise KeyError(plan_id)


def _trigger_name(plan: dict) -> str:
    for action in plan.get("action") or []:
        trigger = (action.get("trigger") or [{}])[0]
        name = trigger.get("name")
        if name:
            return str(name)
    return ""


@pytest.mark.parametrize("plan_id", _GATE4_DURABLE_PLAN_IDS)
def test_gate4_plans_declare_durable_pubsub(plan_id: str) -> None:
    plan = _plan_by_id(plan_id)
    assert plan.get("_workflowMode") == "durable_pubsub"


@pytest.mark.parametrize("plan_id", _GATE4_DURABLE_PLAN_IDS)
def test_gate4_plans_enable_durable_runner(plan_id: str, monkeypatch) -> None:
    monkeypatch.delenv("DURABLE_ENGINE_DISABLED", raising=False)
    assert is_durable_runner_enabled(plan_id) is True


def test_gold_training_trigger_matches_api_event() -> None:
    plan = _plan_by_id("pd-gold-training-audit")
    assert _trigger_name(plan) == "gold-training-run"


def test_episode_bundle_trigger_matches_bus_event() -> None:
    plan = _plan_by_id("pd-episode-bundle-coding")
    assert _trigger_name(plan) == "episode_bundle"


def test_validation_plans_use_validation_run_trigger() -> None:
    for plan in [*VALIDATION_PLAN_DEFINITIONS, REFERRAL_TRIAGE_PLAN_DEFINITION]:
        if plan["id"] == "pd-referral-triage-e2e":
            assert _trigger_name(plan) == "referral-triage-requested"
            continue
        assert _trigger_name(plan) == "validation-run-requested"


def test_episode_bundle_chain_is_linear_coding_path() -> None:
    plan = _plan_by_id("pd-episode-bundle-coding")
    subgraphs = [action.get("_subgraphId") for action in plan["action"]]
    assert subgraphs == [
        "encounter_loader",
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "coding_verifier",
        "snomed_enrichment",
        "relation_linking",
        "tier_classify",
        "persist",
    ]
