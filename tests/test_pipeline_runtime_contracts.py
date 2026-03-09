from __future__ import annotations

import asyncio

import pytest

from libs.message_bus.base import Message
from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter
from libs.workflow.engine import WorkflowEngine
from app.routers import events as events_router


@pytest.mark.asyncio
async def test_in_memory_bus_honors_scheduled_enqueue_delay():
    bus = InMemoryQueueAdapter()
    received: list[Message] = []
    seen = asyncio.Event()

    async def handler(message: Message):
        received.append(message)
        seen.set()

    await bus.subscribe("pipeline-jobs", handler)
    await bus.send(
        "pipeline-jobs",
        Message(body={"event_type": "timer", "patient_id": "p-1"}),
        schedule_after_seconds=1,
    )

    await asyncio.sleep(0.2)
    assert received == []

    await asyncio.wait_for(seen.wait(), timeout=2.0)
    assert received[0].body["event_type"] == "timer"
    await bus.close()


@pytest.mark.asyncio
async def test_event_router_publishes_pipeline_message(monkeypatch):
    sent: list[tuple[str, Message, int | None]] = []

    class _Bus:
        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            sent.append((queue_or_topic, message, schedule_after_seconds))

        async def close(self):
            return None

    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: _Bus(),
    )

    response = await events_router.receive_lab_result(
        events_router.LabResultPayload(
            patient_id="p-1",
            test_code="HbA1c",
            result_value="72",
        )
    )

    assert response["status"] == "queued"
    assert sent[0][0] == events_router.PIPELINE_QUEUE
    assert sent[0][1].body["event_type"] == "new-result"
    assert sent[0][1].subject == "new-result"


@pytest.mark.asyncio
async def test_workflow_engine_schedule_timer_wraps_message():
    sent: list[tuple[str, Message, int | None]] = []

    class _Bus:
        async def send(self, queue_or_topic, message, *, schedule_after_seconds=None):
            sent.append((queue_or_topic, message, schedule_after_seconds))

    engine = WorkflowEngine(message_bus=_Bus())
    await engine.schedule_timer("plan-1", "action-1", "patient-1", 30)

    assert len(sent) == 1
    assert sent[0][0] == "pipeline-jobs"
    assert sent[0][2] == 30
    assert isinstance(sent[0][1], Message)
    assert sent[0][1].body["event_type"] == "timer"
