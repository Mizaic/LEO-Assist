"""Gate 5 G5.2 -- deterministic durable replay with stage output hashes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    DurableStepRunner,
    _Action,
)
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from tests.helpers.claim_race_client import InMemoryClaimClient
from tests.helpers.stage_replay import (
    RECORDED_LLM_EXTRACTION,
    RECORDED_POST_PROCESSING,
    stage_output_hash,
)


def _manifest(*actions: _Action) -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=1,
        version_node_id="ver-replay-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=tuple(actions),
    )


def _body(action_id: str, run_id: str = "run-replay-1") -> dict:
    return {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": action_id,
        "step_id": action_id,
        "plan_definition_id": "pd-referral-assessment",
        "run_id": run_id,
        "patient_id": "p-replay-1",
    }


@pytest.mark.asyncio
async def test_replay_preserves_stage_output_hash() -> None:
    """Second delivery returns the same output hash without re-invoking LLM."""
    extract = _Action(action_id="act-ref-extract", subgraph_id="extraction")
    client = InMemoryClaimClient()
    llm_calls: list[int] = []

    def _invoke(_state: dict) -> dict:
        llm_calls.append(1)
        return {"entities": RECORDED_LLM_EXTRACTION["win1"]}

    mock_graph = MagicMock()
    mock_graph.invoke = _invoke
    mock_bus = AsyncMock()

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(extract),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-replay-1"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        first = await DurableStepRunner.run_step(_body("act-ref-extract"), bus=mock_bus)
        second = await DurableStepRunner.run_step(
            _body("act-ref-extract"), bus=mock_bus
        )

    first_hash = stage_output_hash(first.output)
    second_hash = stage_output_hash(second.output)
    assert first_hash == second_hash
    assert llm_calls == [1]
    assert "already_completed" in second.warnings


@pytest.mark.asyncio
async def test_multi_stage_recorded_responses_produce_stable_hashes() -> None:
    """Three-stage chain with recorded outputs yields identical hashes on replay."""
    stages = (
        _Action(action_id="act-ref-extract", subgraph_id="extraction"),
        _Action(
            action_id="act-ref-post-process",
            subgraph_id="post_processing",
            related_actions=[{"actionId": "act-ref-extract"}],
        ),
        _Action(
            action_id="act-ref-relation-link",
            subgraph_id="relation_linking",
            related_actions=[{"actionId": "act-ref-post-process"}],
        ),
    )
    client = InMemoryClaimClient()
    run_id = "run-replay-multi"
    recorded_hashes: dict[str, str] = {}
    invoke_counts: dict[str, int] = {}

    outputs = {
        "extraction": {"entities": RECORDED_LLM_EXTRACTION["win1"]},
        "post_processing": dict(RECORDED_POST_PROCESSING),
        "relation_linking": {"relations": [{"from": "c0", "to": "c1"}]},
    }

    def _build(subgraph_id: str) -> MagicMock:
        graph = MagicMock()

        def _invoke(_state: dict) -> dict:
            invoke_counts[subgraph_id] = invoke_counts.get(subgraph_id, 0) + 1
            return dict(outputs[subgraph_id])

        graph.invoke = _invoke
        return graph

    mock_bus = AsyncMock()
    action_ids = [s.action_id for s in stages]

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(*stages),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-replay-1"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(
                build=MagicMock(side_effect=lambda sid: _build(sid))
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        for action_id in action_ids:
            result = await DurableStepRunner.run_step(
                _body(action_id, run_id=run_id), bus=mock_bus
            )
            recorded_hashes[action_id] = stage_output_hash(result.output)

        for action_id in action_ids:
            replay = await DurableStepRunner.run_step(
                _body(action_id, run_id=run_id), bus=mock_bus
            )
            assert stage_output_hash(replay.output) == recorded_hashes[action_id]
            assert "already_completed" in replay.warnings

    assert invoke_counts == {s.subgraph_id: 1 for s in stages}


def test_in_memory_store_replay_from_completed_stage() -> None:
    """Direct store replay: already_completed returns prior output hash."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="extraction",
        run_id="run-store-replay",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-1",
    )
    store.upsert_run(request, status="running")
    claim = store.claim_stage(request, {}, lease_owner="w1", lease_seconds=3600)
    output = {"entities": RECORDED_LLM_EXTRACTION["win1"]}
    store.complete_stage(
        request,
        StepResult(status="completed", output=output),
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )
    expected_hash = stage_output_hash(output)

    replay = store.claim_stage(request, {}, lease_owner="w2", lease_seconds=3600)
    assert replay.outcome == "already_completed"
    assert stage_output_hash(replay.output or {}) == expected_hash

    stage = client.stages[stage_run_id(request.run_id, request.step_id)]
    assert stage["status"] == "completed"
