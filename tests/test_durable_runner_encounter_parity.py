"""Parity test: DurableStepRunner step sequence for pd-gp-encounter-coding.

Verifies that the relatedActions chain in the GP Encounter plan:
1. Has _workflowMode: durable_pubsub
2. Starts from encounter_loader (act-load-encounter triggers encounter-created)
3. Contains the LLM coding verifier (act-coding-verify) in the chain
4. Has no placeholder subgraphIds

Also tests DurableStepRunner.start() handling of a real-action trigger
(encounter_loader is a real subgraph, not a no-op trigger node).
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.workflow.durable_step_runner import DURABLE_STEP_EVENT


def _load_plan_def(plan_id: str) -> dict:
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
    by_id = {a["id"]: a for a in actions}
    successor: dict[str, str] = {}
    for a in actions:
        for rel in a.get("relatedAction") or []:
            predecessor = rel.get("actionId")
            if predecessor:
                successor[predecessor] = a["id"]
    # Start from the first action (sequence 0)
    start = min(actions, key=lambda x: x.get("_sequence", 999))
    ordered = []
    current_id = start["id"]
    visited: set[str] = set()
    while current_id:
        if current_id in visited:
            break
        visited.add(current_id)
        action = by_id[current_id]
        ordered.append(action.get("_subgraphId", ""))
        current_id = successor.get(current_id)
    return ordered


# ---------------------------------------------------------------------------
# Seed structure tests
# ---------------------------------------------------------------------------


def test_gp_encounter_has_durable_pubsub_workflow_mode():
    plan = _load_plan_def("pd-gp-encounter-coding")
    assert plan.get("_workflowMode") == "durable_pubsub"


def test_gp_encounter_chain_starts_with_encounter_loader():
    plan = _load_plan_def("pd-gp-encounter-coding")
    chain = _walk_action_chain(plan["action"])
    assert chain[0] == "encounter_loader", f"Expected encounter_loader, got {chain[0]}"


def test_gp_encounter_chain_contains_coding_verifier():
    plan = _load_plan_def("pd-gp-encounter-coding")
    chain = _walk_action_chain(plan["action"])
    assert "coding_verifier" in chain, f"coding_verifier not found in chain: {chain}"


def test_gp_encounter_coding_verifier_before_coding_route():
    """coding_verifier must come before the final condition (coding-route) node."""
    plan = _load_plan_def("pd-gp-encounter-coding")
    chain = _walk_action_chain(plan["action"])
    assert "coding_verifier" in chain
    assert chain.count("condition") >= 2, "Expected at least 2 condition nodes"
    verifier_idx = chain.index("coding_verifier")
    # The coding-route is the last condition node; extraction-route is first.
    last_condition_idx = len(chain) - 1 - chain[::-1].index("condition")
    assert verifier_idx < last_condition_idx, (
        f"coding_verifier (idx {verifier_idx}) must come before "
        f"the last condition/coding-route (idx {last_condition_idx})"
    )


def test_gp_encounter_no_placeholder_subgraph_ids():
    plan = _load_plan_def("pd-gp-encounter-coding")
    placeholder_ids = {"durable_step", ""}
    for action in plan["action"]:
        subgraph_id = action.get("_subgraphId", "")
        assert (
            subgraph_id not in placeholder_ids
        ), f"Action '{action['id']}' uses placeholder subgraphId '{subgraph_id}'"


def test_gp_encounter_plan_pins_version_rollout():
    plan = _load_plan_def("pd-gp-encounter-coding")
    rollout = plan.get("_versionRollout") or {}
    assert rollout.get("defaultVersion") == "latest"


def test_gp_encounter_chain_matches_clinical_happy_path():
    """Main pass-through branch must preserve source->extract->code->persist order."""
    plan = _load_plan_def("pd-gp-encounter-coding")
    chain = _walk_action_chain(plan["action"])
    expected_prefix = [
        "encounter_loader",
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "condition",
        "terminology",
        "coding_verifier",
        "snomed_enrichment",
        "relation_linking",
        "condition",
        "tier_classify",
        "persist",
    ]
    assert chain[: len(expected_prefix)] == expected_prefix


@pytest.mark.asyncio
async def test_encounter_extract_dual_delivery_executes_subgraph_once():
    """Two deliveries of the same durable stage run the subgraph exactly once."""
    from tests.helpers.claim_race_client import InMemoryClaimClient

    from libs.workflow.durable_step_runner import DurableStepRunner, _Action
    from libs.workflow.plan_manifest import PlanManifest

    action = _Action(action_id="act-extract", subgraph_id="extraction")
    manifest = PlanManifest(
        plan_id="pd-gp-encounter-coding",
        version_id=1,
        version_node_id="ver-enc-dual",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=(action,),
    )
    client = InMemoryClaimClient()
    mock_bus = AsyncMock()
    executions: list[int] = []
    mock_graph = MagicMock()

    def _invoke(_state):
        executions.append(1)
        return {"entities": []}

    mock_graph.invoke = _invoke
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-extract",
        "step_id": "act-extract",
        "plan_definition_id": "pd-gp-encounter-coding",
        "run_id": "run-enc-dual",
        "patient_id": "p-enc-dual",
    }
    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=manifest,
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-enc-dual"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        first = await DurableStepRunner.run_step(body, bus=mock_bus)
        second = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert first.status == "completed"
    assert second.status == "completed"
    assert "already_completed" in second.warnings
    assert executions == [1]


# ---------------------------------------------------------------------------
# DurableStepRunner.start behaviour for real-action trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_publishes_encounter_loader_directly():
    """encounter_loader has trigger_name and node_type=action -- start() publishes it."""
    from libs.workflow.durable_step_runner import DurableStepRunner, _Action
    from libs.workflow.plan_manifest import PlanManifest

    encounter_loader = _Action(
        action_id="act-load-encounter",
        subgraph_id="encounter_loader",
        node_type="action",
        trigger_name="encounter-created",
    )
    extract_action = _Action(
        action_id="act-extract",
        subgraph_id="extraction",
        related_actions=[{"actionId": "act-load-encounter"}],
    )
    manifest = PlanManifest(
        plan_id="pd-gp-encounter-coding",
        version_id=1,
        version_node_id="ver-enc-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=(encounter_loader, extract_action),
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()

    body = {
        "event_type": "encounter-created",
        "plan_definition_id": "pd-gp-encounter-coding",
        "run_id": "run-enc-001",
        "patient_id": "p-enc-001",
        "encounter_id": "e-enc-001",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_plan_manifest",
            return_value=manifest,
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                admit_run=MagicMock(
                    return_value=MagicMock(
                        run_id="run-enc-001",
                        created=True,
                        first_step_enqueued=False,
                        status="running",
                    )
                ),
                claim_first_step_enqueue=MagicMock(return_value=True),
            ),
        ),
    ):
        await DurableStepRunner.start(body, bus=mock_bus)

    mock_bus.send.assert_called_once()
    sent_body = mock_bus.send.call_args[0][1].body
    # Should publish act-load-encounter itself, NOT act-extract
    assert sent_body["action_id"] == "act-load-encounter"
