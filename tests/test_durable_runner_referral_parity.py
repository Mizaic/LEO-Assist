"""Parity test: DurableStepRunner step sequence matches REFERRAL_STEPS.

Verifies that the relatedActions chain in pd-referral-assessment produces
the same ordered step sequence as the hard-coded REFERRAL_STEPS tuple so
that migrating to DurableStepRunner does not silently drop or reorder steps.

This is a structural test -- it does not call Neo4j or Azure Service Bus.
It loads the seed definition from scripts/seed_plan_definitions.py and
walks the relatedActions graph, then compares subgraph IDs in order against
the REFERRAL_STEPS definitions.
"""

from __future__ import annotations

import sys
import os

import pytest


# ---------------------------------------------------------------------------
# Load the seed script (no Neo4j connection needed -- we just read the data)
# ---------------------------------------------------------------------------


def _load_plan_def(plan_id: str) -> dict:
    # Adjust sys.path so the seed script is importable as a module.
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    scripts_dir = os.path.join(repo_root, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "seed_plan_definitions",
        os.path.join(scripts_dir, "seed_plan_definitions.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for pd in mod.PLAN_DEFINITIONS:
        if pd["id"] == plan_id:
            return pd
    raise KeyError(f"Plan '{plan_id}' not found in PLAN_DEFINITIONS")


def _walk_action_chain(actions: list[dict]) -> list[str]:
    """Walk relatedActions to produce an ordered list of subgraphIds.

    Starts from the trigger action and follows the chain until no next
    action exists.
    """
    by_id = {a["id"]: a for a in actions}
    # Build successor map: predecessor_id -> successor_id
    successor: dict[str, str] = {}
    for a in actions:
        for rel in a.get("relatedAction") or []:
            predecessor = rel.get("actionId")
            if predecessor:
                successor[predecessor] = a["id"]

    # Find trigger start
    trigger = next(
        (a for a in actions if a.get("trigger") or a.get("_nodeType") == "trigger"),
        None,
    )
    if trigger is None:
        return []

    ordered = []
    current_id = trigger["id"]
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            break
        visited.add(current_id)
        action = by_id[current_id]
        subgraph_id = action.get("_subgraphId", "")
        if subgraph_id not in {"trigger", "durable_referral_workflow", ""}:
            ordered.append(subgraph_id)
        current_id = successor.get(current_id)

    return ordered


# ---------------------------------------------------------------------------
# Expected order from REFERRAL_STEPS (the ground truth)
# ---------------------------------------------------------------------------

EXPECTED_SUBGRAPH_ORDER = [
    "extraction",
    "post_processing",
    "relation_linking",
    "extraction_check",
    "terminology",
    "coding_verifier",
    "persist",
    "referral_reason",
    "compliance",
    "quality_check",
    "sbar",
]


def test_referral_action_chain_matches_referral_steps():
    plan = _load_plan_def("pd-referral-assessment")
    actual = _walk_action_chain(plan["action"])
    assert actual == EXPECTED_SUBGRAPH_ORDER, (
        f"Step order mismatch.\n"
        f"Expected: {EXPECTED_SUBGRAPH_ORDER}\n"
        f"Got:      {actual}"
    )


def test_referral_plan_has_durable_pubsub_workflow_mode():
    plan = _load_plan_def("pd-referral-assessment")
    assert plan.get("_workflowMode") == "durable_pubsub"


def test_terminal_action_has_completion_metadata():
    plan = _load_plan_def("pd-referral-assessment")
    sbar_action = next(a for a in plan["action"] if a["id"] == "act-ref-sbar")
    assert sbar_action.get("_completionQueue") == "referral-assessments-output"
    assert sbar_action.get("_completionEventType") == "referral_assessment_completed"


def test_all_non_trigger_actions_have_real_subgraph_ids():
    plan = _load_plan_def("pd-referral-assessment")
    placeholder_ids = {"durable_step", "durable_referral_workflow", ""}
    for action in plan["action"]:
        node_type = action.get("_nodeType", "action")
        subgraph_id = action.get("_subgraphId", "")
        if node_type in {"trigger"} or action.get("trigger"):
            continue
        assert subgraph_id not in placeholder_ids, (
            f"Action '{action['id']}' still uses placeholder subgraphId '{subgraph_id}'"
        )
