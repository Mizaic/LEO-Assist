"""Gate 5 -- repair successor outbox on already_completed replay."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from libs.message_bus.base import Message
from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    DurableStepRunner,
    _Action,
)
from libs.workflow.durable_steps import StepRequest
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from tests.helpers.claim_race_client import InMemoryClaimClient


def _manifest(*actions: _Action) -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=1,
        version_node_id="ver-repair-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=tuple(actions),
    )


def _body(action_id: str, run_id: str = "run-repair-1") -> dict:
    return {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": action_id,
        "step_id": action_id,
        "plan_definition_id": "pd-referral-assessment",
        "run_id": run_id,
        "patient_id": "p-repair-1",
    }


@pytest.mark.asyncio
async def test_already_completed_repairs_missing_successor_outbox() -> None:
    """Completed stage with no outbox rows still enqueues the next action."""
    post_process = _Action(
        action_id="act-ref-post-process",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-ref-extract"}],
    )
    relation_link = _Action(
        action_id="act-ref-relation-link",
        subgraph_id="relation_linking",
        related_actions=[{"actionId": "act-ref-post-process"}],
    )
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-repair-1",
        workflow_id="pd-referral-assessment",
        plan_definition_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-repair-1",
    )
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)
    client.stages[stage_id] = {
        "status": "completed",
        "output_json": json.dumps({"entities": []}),
        "next_action_ids_json": json.dumps(["act-ref-relation-link"]),
        "next_published": True,
        "run_id": request.run_id,
        "step_id": request.step_id,
        "attempt": 1,
        "lease_generation": 1,
    }
    assert client.stage_outbox.get(stage_id) in (None, [])

    mock_bus = AsyncMock()
    sent_targets: list[str] = []

    async def _capture_send(queue: str, message: Message) -> None:
        sent_targets.append(str(message.body.get("action_id") or ""))

    mock_bus.send = AsyncMock(side_effect=_capture_send)

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(post_process, relation_link),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-repair-1", "entities": []},
        ),
    ):
        result = await DurableStepRunner.run_step(
            _body("act-ref-post-process"), bus=mock_bus
        )

    assert result.status == "completed"
    assert "already_completed" in result.warnings
    assert sent_targets == ["act-ref-relation-link"]
    pending = store.load_pending_outbox(request)
    assert pending == []


def test_successors_need_enqueue_when_successor_stage_missing() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-need-enq",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-1",
    )
    store.upsert_run(request, status="running")
    assert store.successors_need_enqueue(request.run_id, ["act-ref-relation-link"])


def test_successors_need_enqueue_false_when_successor_running() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    run_id = "run-running-successor"
    store.upsert_run(
        StepRequest(
            event_type="post_processing",
            run_id=run_id,
            workflow_id="pd-referral-assessment",
            step_id="act-ref-post-process",
            patient_id="p-1",
        ),
        status="running",
    )
    successor = StepRequest(
        event_type="relation_linking",
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        step_id="act-ref-relation-link",
        patient_id="p-1",
    )
    claim = store.claim_stage(successor, {}, lease_owner="worker-b", lease_seconds=3600)
    assert claim.outcome == "claimed"
    assert not store.successors_need_enqueue(run_id, ["act-ref-relation-link"])


def test_should_repair_when_outbox_missing_despite_next_published() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-repair-check",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-1",
    )
    store.upsert_run(request, status="running")
    assert store.should_repair_successor_outbox(
        request,
        ["act-ref-relation-link"],
        next_published=True,
    )


def test_should_not_repair_when_outbox_already_sent() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-sent-check",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-1",
    )
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)
    client.stage_outbox[stage_id] = ["evt-sent-1"]
    client.outbox["evt-sent-1"] = {"id": "evt-sent-1", "status": "sent"}
    assert not store.should_repair_successor_outbox(
        request,
        ["act-ref-relation-link"],
        next_published=True,
    )


def test_should_requeue_sent_orphan_when_successor_missing() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-orphan-check",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-1",
    )
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)
    client.stage_outbox[stage_id] = ["evt-sent-1"]
    client.outbox["evt-sent-1"] = {
        "id": "evt-sent-1",
        "status": "sent",
        "sent_at": "2020-01-01T00:00:00+00:00",
    }
    assert store.should_requeue_sent_orphan_outbox(
        request,
        ["act-ref-relation-link"],
        next_published=True,
    )


def test_should_not_requeue_sent_orphan_inside_cooldown() -> None:
    from datetime import datetime, timezone

    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-cooldown-check",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-1",
    )
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)
    now = datetime(2026, 7, 29, 10, 0, tzinfo=timezone.utc)
    client.stage_outbox[stage_id] = ["evt-sent-1"]
    client.outbox["evt-sent-1"] = {
        "id": "evt-sent-1",
        "status": "sent",
        "sent_at": now.isoformat(),
    }
    assert not store.should_requeue_sent_orphan_outbox(
        request,
        ["act-ref-relation-link"],
        next_published=True,
        now=now,
    )


@pytest.mark.asyncio
async def test_already_completed_requeues_sent_orphan_once() -> None:
    """Sent-orphan successors are re-queued once; cooldown blocks storms."""
    post_process = _Action(
        action_id="act-ref-post-process",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-ref-extract"}],
    )
    relation_link = _Action(
        action_id="act-ref-relation-link",
        subgraph_id="relation_linking",
        related_actions=[{"actionId": "act-ref-post-process"}],
    )
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = StepRequest(
        event_type="post_processing",
        run_id="run-storm-1",
        workflow_id="pd-referral-assessment",
        plan_definition_id="pd-referral-assessment",
        step_id="act-ref-post-process",
        patient_id="p-storm-1",
    )
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)
    client.stages[stage_id] = {
        "status": "completed",
        "output_json": json.dumps({"entities": []}),
        "next_action_ids_json": json.dumps(["act-ref-relation-link"]),
        "next_published": True,
        "run_id": request.run_id,
        "step_id": request.step_id,
        "attempt": 1,
        "lease_generation": 1,
    }
    from libs.workflow.pipeline_outbox import (
        build_durable_step_message_id,
        build_edge_version,
        build_outbox_event_id,
    )

    target = "act-ref-relation-link"
    edge_version = build_edge_version({"actionId": "act-ref-post-process"})
    event_id = build_outbox_event_id(request.run_id, stage_id, target, edge_version)
    message_id = build_durable_step_message_id(
        request.run_id, stage_id, target, edge_version
    )
    body = json.dumps(
        {
            "event_type": DURABLE_STEP_EVENT,
            "action_id": target,
            "step_id": target,
            "run_id": request.run_id,
        }
    )
    client.outbox[event_id] = {
        "id": event_id,
        "message_id": message_id,
        "queue_name": "pipeline-jobs",
        "body_json": body,
        "status": "sent",
        "sent_at": "2020-01-01T00:00:00+00:00",
    }
    client.stage_outbox[stage_id] = [event_id]

    mock_bus = AsyncMock()
    sent_targets: list[str] = []

    async def _capture_send(queue: str, message: Message) -> None:
        sent_targets.append(str(message.body.get("action_id") or ""))

    mock_bus.send = AsyncMock(side_effect=_capture_send)

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(post_process, relation_link),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-storm-1", "entities": []},
        ),
    ):
        for _ in range(5):
            result = await DurableStepRunner.run_step(
                _body("act-ref-post-process", run_id="run-storm-1"),
                bus=mock_bus,
            )
            assert result.status == "completed"
            assert "already_completed" in result.warnings

    assert sent_targets == ["act-ref-relation-link"]
    assert mock_bus.send.await_count == 1
