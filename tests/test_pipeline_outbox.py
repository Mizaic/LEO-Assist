"""D1.10 / D1.11 -- edge outbox and deterministic message IDs."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from libs.message_bus.base import Message
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_outbox import (
    build_durable_step_message_id,
    build_edge_version,
    build_first_step_message_id,
    build_outbox_event_id,
    build_successor_outbox_events,
    dispatch_stage_outbox,
)
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id


def _request() -> StepRequest:
    return StepRequest(
        event_type="durable_step",
        run_id="run-outbox-1",
        workflow_id="pd-referral-assessment",
        plan_definition_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-outbox-1",
    )


def test_edge_version_stable_for_same_edge() -> None:
    edge = {"actionId": "act-a", "sourceHandle": "ok", "targetHandle": "in"}
    assert build_edge_version(edge) == build_edge_version(dict(edge))


def test_outbox_and_message_ids_are_deterministic() -> None:
    run_id = "run-outbox-1"
    stage_id = stage_run_id(run_id, "act-ref-extract")
    target = "act-ref-post"
    edge_version = build_edge_version({"actionId": "act-ref-extract"})
    outbox_id = build_outbox_event_id(run_id, stage_id, target, edge_version)
    message_id = build_durable_step_message_id(run_id, stage_id, target, edge_version)
    assert outbox_id == build_outbox_event_id(run_id, stage_id, target, edge_version)
    assert message_id == build_durable_step_message_id(
        run_id, stage_id, target, edge_version
    )
    assert outbox_id != message_id


def test_complete_stage_creates_pending_outbox_events() -> None:
    client = MagicMock()
    client.run.return_value = [{"outcome": "completed", "outbox_created": 2}]
    store = PipelineStageStore(client)
    request = _request()
    edges = [
        {"target": "act-ref-post", "sourceHandle": "default", "targetHandle": None},
        {"target": "act-ref-notify", "sourceHandle": "default", "targetHandle": None},
    ]
    store.complete_stage(
        request,
        StepResult(status="completed", output={"ok": True}),
        next_action_ids=["act-ref-post", "act-ref-notify"],
        successor_edges=edges,
        queue_name="pipeline-jobs",
        lease_owner="worker-a",
        lease_generation=1,
    )
    kwargs = client.run.call_args.kwargs
    outbox_events = kwargs["outbox_events"]
    assert len(outbox_events) == 2
    assert {item["target_action_id"] for item in outbox_events} == {
        "act-ref-post",
        "act-ref-notify",
    }
    assert all(item["status"] == "pending" for item in outbox_events)


@pytest.mark.asyncio
async def test_dispatch_stage_outbox_sends_pending_and_marks_sent() -> None:
    request = _request()
    stage_id = stage_run_id(request.run_id, request.step_id)
    edge_version = build_edge_version({"actionId": request.step_id})
    target = "act-ref-post"
    event_id = build_outbox_event_id(request.run_id, stage_id, target, edge_version)
    message_id = build_durable_step_message_id(
        request.run_id, stage_id, target, edge_version
    )
    body = {"event_type": "durable_step", "action_id": target, "run_id": request.run_id}

    store = MagicMock()
    store.load_pending_outbox.return_value = [
        {
            "id": event_id,
            "message_id": message_id,
            "queue_name": "pipeline-jobs",
            "body_json": json.dumps(body),
        }
    ]
    store.try_claim_outbox_for_send.return_value = {
        "id": event_id,
        "message_id": message_id,
        "queue_name": "pipeline-jobs",
        "body_json": json.dumps(body),
    }
    store.has_pending_outbox.return_value = False
    bus = AsyncMock()

    sent = await dispatch_stage_outbox(store, bus, request)

    assert sent == 1
    bus.send.assert_called_once()
    queue, message = bus.send.call_args[0]
    assert queue == "pipeline-jobs"
    assert isinstance(message, Message)
    assert message.message_id == message_id
    assert message.body["action_id"] == target
    store.try_claim_outbox_for_send.assert_called_once_with(event_id, request)
    store.mark_outbox_sent.assert_not_called()
    store.mark_next_published.assert_called_once_with(request)


def test_first_step_message_id_is_deterministic() -> None:
    run_id = "run-outbox-1"
    action_id = "act-ref-extract"
    assert build_first_step_message_id(run_id, action_id) == build_first_step_message_id(
        run_id, action_id
    )
    assert build_first_step_message_id(run_id, action_id) != build_first_step_message_id(
        run_id, "act-other"
    )


@pytest.mark.asyncio
async def test_dispatch_stage_outbox_second_claim_skips_send() -> None:
    request = _request()
    stage_id = stage_run_id(request.run_id, request.step_id)
    edge_version = build_edge_version({"actionId": request.step_id})
    target = "act-ref-post"
    event_id = build_outbox_event_id(request.run_id, stage_id, target, edge_version)
    message_id = build_durable_step_message_id(
        request.run_id, stage_id, target, edge_version
    )
    body = {"event_type": "durable_step", "action_id": target, "run_id": request.run_id}

    store = MagicMock()
    store.load_pending_outbox.return_value = [
        {
            "id": event_id,
            "message_id": message_id,
            "queue_name": "pipeline-jobs",
            "body_json": json.dumps(body),
        }
    ]
    store.try_claim_outbox_for_send.return_value = None
    store.has_pending_outbox.return_value = False
    bus = AsyncMock()

    sent = await dispatch_stage_outbox(store, bus, request)

    assert sent == 0
    bus.send.assert_not_called()
    store.mark_next_published.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_concurrent_dispatch_sends_successor_once() -> None:
    from tests.helpers.claim_race_client import InMemoryClaimClient

    request = _request()
    stage_id = stage_run_id(request.run_id, request.step_id)
    edge_version = build_edge_version({"actionId": request.step_id})
    target = "act-ref-post"
    events = build_successor_outbox_events(
        request,
        stage_run_id=stage_id,
        next_action_ids=[target],
        successor_edges=[{"target": target, "actionId": request.step_id}],
        queue_name="pipeline-jobs",
        body_template={
            "event_type": "durable_step",
            "run_id": request.run_id,
            "plan_definition_id": request.plan_definition_id,
        },
    )
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    store.upsert_run(request, status="running")
    client.stages[stage_id] = {
        "status": "completed",
        "run_id": request.run_id,
        "step_id": request.step_id,
        "next_published": False,
    }
    for evt in events:
        client.outbox[evt["id"]] = dict(evt)
        client.stage_outbox.setdefault(stage_id, []).append(evt["id"])

    bus = AsyncMock()
    results = await asyncio.gather(
        dispatch_stage_outbox(store, bus, request),
        dispatch_stage_outbox(store, bus, request),
    )

    assert sum(results) == 1
    bus.send.assert_called_once()
    assert client.stages[stage_id]["next_published"] is True
