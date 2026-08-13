"""U4.1 -- referral assessment reference certification suite.

Bundles capability conformance, durable pub/sub contract, and Gate 3 clinical
unit tests that must pass before Gate 4 GP coding migration.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from libs.pipeline_graph.capability_registry import (
    get_capability_registry,
    validate_plan_snapshot,
)
from libs.workflow.referral_policy import (
    DEFAULT_REFERRAL_POLICY,
    validate_referral_policy,
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


def _referral_plan() -> dict:
    mod = _load_seed_module()
    for plan in mod.PLAN_DEFINITIONS:
        if plan.get("id") == "pd-referral-assessment":
            return plan
    raise KeyError("pd-referral-assessment not found")


def test_u4_1_referral_plan_passes_capability_conformance() -> None:
    plan = _referral_plan()
    errors = validate_plan_snapshot(plan, registry=get_capability_registry())
    assert errors == [], f"capability validation failed: {errors}"


def test_u4_1_default_referral_policy_is_valid() -> None:
    errors = validate_referral_policy(DEFAULT_REFERRAL_POLICY)
    assert errors == []


def test_u4_1_referral_plan_pins_gate3_policy_fields() -> None:
    plan = _referral_plan()
    policy = plan.get("_referralPolicy") or DEFAULT_REFERRAL_POLICY
    assert policy["extraction"]["windowSize"] == 10
    assert policy["extraction"]["contextMode"] == "window_local"
    assert policy["extraction"]["maxWindowInputTokens"] == 16000
    assert policy["recall"]["maxChunkFetches"] == 5
    assert policy["prompts"]["recall"]["name"] == "sbar_recall"


def test_u4_1_referral_plan_declares_durable_pubsub() -> None:
    plan = _referral_plan()
    assert plan.get("_workflowMode") == "durable_pubsub"


@pytest.mark.parametrize(
    "module_path",
    [
        "tests.test_gate3_orchestrator_wiring",
        "tests.test_gate3_extraction_window",
        "tests.test_gate3_bounded_recall",
        "tests.test_gate3_uncoded_coverage",
        "tests.test_gate3_background_envelope",
        "tests.test_gate3_situation_structured_first",
        "tests.test_referral_durable_pubsub",
        "tests.test_durable_runner_referral_parity",
        "tests.test_platform_conformance",
    ],
)
def test_u4_1_gate3_clinical_gold_modules_import(module_path: str) -> None:
    """Each certification module must import cleanly (CI discovery guard)."""
    import importlib

    importlib.import_module(module_path)
