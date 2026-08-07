"""Fail-fast durable pipeline: terminal run failure on any stage error."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.message_bus.settlement import resolve_durable_step_settlement
from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    DurableStepRunner,
    _Action,
)
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from libs.workflow.pipeline_stuck_recovery import recover_stuck_pipeline_run
from tests.helpers.claim_race_client import InMemoryClaimClient
from tests.test_durable_step_runner import _manifest


def _request(run_id: str, step_id: str) -> StepRequest:
    return StepRequest(
        event_type=DURABLE_STEP_EVENT,
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        plan_definition_id="pd-referral-assessment",
        step_id=step_id,
        patient_id="p-fail",
    )


def test_complete_stage_marks_run_failed_without_outbox() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-fail-store", "act-a")
    store.upsert_run(request, status="running")
    claim = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    assert claim.outcome == "claimed"

    store.complete_stage(
        request,
        StepResult(status="failed", errors=["boom"]),
        next_action_ids=["act-b"],
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )

    assert client.runs[request.run_id]["status"] == "failed"
    stage = client.stages[stage_run_id(request.run_id, request.step_id)]
    assert stage["status"] == "failed"
    assert stage.get("lease_owner") is None
    assert not store.load_pending_outbox(request)


def test_complete_stage_errors_on_completed_status_fail_run() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-fail-errors", "act-a")
    store.upsert_run(request, status="running")
    claim = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)

    store.complete_stage(
        request,
        StepResult(status="completed", errors=["subgraph_error"]),
        next_action_ids=["act-b"],
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )

    assert client.runs[request.run_id]["status"] == "failed"
    assert not store.load_pending_outbox(request)


@pytest.mark.asyncio
async def test_run_step_failure_does_not_dispatch_successors() -> None:
    current = _Action(action_id="act-a", subgraph_id="extraction")
    nxt = _Action(
        action_id="act-b",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-a"}],
    )
    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"errors": ["extract failed"]})
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-a",
        "step_id": "act-a",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-fail-step",
        "patient_id": "p-fail",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current, nxt),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
        ) as dispatch_mock,
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-fail"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        client = InMemoryClaimClient()
        store = PipelineStageStore(client)
        store.upsert_run(_request("run-fail-step", "act-a"), status="running")
        with patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ):
            result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "failed"
    assert client.runs["run-fail-step"]["status"] == "failed"
    dispatch_mock.assert_not_called()
    mock_bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_run_step_handler_exception_clears_lease_and_fails_run() -> None:
    action = _Action(action_id="act-a", subgraph_id="extraction")
    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(side_effect=RuntimeError("handler blew up"))
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-a",
        "step_id": "act-a",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-fail-exc",
        "patient_id": "p-fail",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(action),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-fail"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        client = InMemoryClaimClient()
        store = PipelineStageStore(client)
        store.upsert_run(_request("run-fail-exc", "act-a"), status="running")
        with patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ):
            result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "failed"
    stage = client.stages[stage_run_id("run-fail-exc", "act-a")]
    assert stage["status"] == "failed"
    assert stage.get("lease_owner") is None
    assert client.runs["run-fail-exc"]["status"] == "failed"


@pytest.mark.asyncio
async def test_run_step_warnings_only_dispatches_successors() -> None:
    current = _Action(action_id="act-a", subgraph_id="terminology")
    nxt = _Action(
        action_id="act-b",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-a"}],
    )
    mock_bus = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(
        return_value={
            "warnings": [
                'terminology_low_confidence: 1 entity/entities below score threshold 0.55 -- "dysphagia" (score 0.42)'
            ],
            "errors": [],
        }
    )
    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-a",
        "step_id": "act-a",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-warn-only",
        "patient_id": "p-warn",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current, nxt),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
        ) as dispatch_mock,
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-warn"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        client = InMemoryClaimClient()
        store = PipelineStageStore(client)
        store.upsert_run(_request("run-warn-only", "act-a"), status="running")
        with patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ):
            result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    assert client.runs["run-warn-only"]["status"] == "running"
    dispatch_mock.assert_called_once()


def test_complete_stage_warnings_only_does_not_fail_run() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-warn-store", "act-a")
    store.upsert_run(request, status="running")
    claim = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)

    store.complete_stage(
        request,
        StepResult(
            status="completed",
            warnings=["coding_verifier: 1 entity classified not_codeable"],
        ),
        next_action_ids=["act-b"],
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )

    assert client.runs[request.run_id]["status"] == "running"
    stage = client.stages[stage_run_id(request.run_id, request.step_id)]
    assert stage["status"] == "completed"
    assert store.load_pending_outbox(request)


@pytest.mark.asyncio
async def test_stuck_recovery_skips_failed_run() -> None:
    client = InMemoryClaimClient()
    run_id = "run-fail-stuck"
    store = PipelineStageStore(client)
    request = _request(run_id, "act-a")
    store.upsert_run(request, status="failed")
    client.runs[run_id]["first_step_enqueued"] = True

    bus = AsyncMock()
    sent = await recover_stuck_pipeline_run(client, bus, run_id)
    assert sent == 0
    bus.send.assert_not_called()


def test_failed_step_settlement_completes_message() -> None:
    assert resolve_durable_step_settlement(StepResult(status="failed")) == "complete"
