from __future__ import annotations

import sys
import types

import pytest

from libs.message_bus.base import Message
from services.coding_worker.app.services import job_handler


class _FakeAsyncDriver:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeWorkflowEngine:
    def __init__(self, neo4j_driver=None, message_bus=None):
        self.neo4j_driver = neo4j_driver
        self.message_bus = message_bus


class _FakeServiceBusEventHandler:
    calls: list[dict] = []

    def __init__(self, engine):
        self.engine = engine

    async def handle_message(self, message, *, step_callback=None):
        body = message.body if isinstance(message.body, dict) else {}
        self.calls.append(body)
        if step_callback:
            step_callback(
                {
                    "type": "step_completed",
                    "action_id": "act-extract",
                    "subgraph_id": "extraction",
                    "status": "completed",
                    "duration_ms": 1,
                    "entity_count": 1,
                }
            )
            step_callback({"type": "run_completed", "status": "completed"})
        return {"status": "completed"}


class _FakePatientGraphClient:
    rows: list[dict] = []

    def run(self, _query: str, **_kwargs):
        return list(self.rows)

    def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_extract_encounter_routes_through_workflow_engine(monkeypatch):
    published: list[dict] = []
    _FakeServiceBusEventHandler.calls = []
    fake_driver = _FakeAsyncDriver()

    monkeypatch.setattr(
        "libs.neo4j_client.client.get_async_driver",
        lambda: fake_driver,
    )
    monkeypatch.setitem(
        sys.modules,
        "libs.workflow.engine",
        types.SimpleNamespace(WorkflowEngine=_FakeWorkflowEngine),
    )
    monkeypatch.setattr(
        "libs.workflow.events.ServiceBusEventHandler",
        _FakeServiceBusEventHandler,
    )
    monkeypatch.setattr(
        "services.coding_worker.app.services.progress_publisher.publish_progress",
        lambda _run_id, event: published.append(event),
    )

    msg = Message(
        body={
            "event_type": "encounter-created",
            "patient_id": "p1",
            "encounter_id": "e1",
            "plan_definition_id": "pd-gp-encounter-coding",
            "mode": "extract_encounter",
            "context": {"dry_run": False},
        },
        correlation_id="run-123",
    )
    await job_handler.handle_coding_job(msg)

    assert len(_FakeServiceBusEventHandler.calls) == 1
    call = _FakeServiceBusEventHandler.calls[0]
    assert call["event_type"] == "encounter-created"
    assert call["encounter_id"] == "e1"
    assert "encounter_text" not in (call.get("context") or {})
    event_types = {e.get("type") for e in published}
    assert "step_completed" in event_types
    assert "run_completed" in event_types
    assert fake_driver.closed is True


@pytest.mark.asyncio
async def test_extract_patient_fans_out_per_encounter(monkeypatch):
    published: list[dict] = []
    _FakeServiceBusEventHandler.calls = []
    fake_driver = _FakeAsyncDriver()

    fake_pg = _FakePatientGraphClient()
    fake_pg.rows = [{"encounter_id": "e1"}, {"encounter_id": ""}, {"encounter_id": "e2"}]

    monkeypatch.setattr(
        "libs.neo4j_client.client.get_async_driver",
        lambda: fake_driver,
    )
    monkeypatch.setattr(
        "libs.neo4j_client.client.PatientGraphClient",
        lambda: fake_pg,
    )
    monkeypatch.setitem(
        sys.modules,
        "libs.workflow.engine",
        types.SimpleNamespace(WorkflowEngine=_FakeWorkflowEngine),
    )
    monkeypatch.setattr(
        "libs.workflow.events.ServiceBusEventHandler",
        _FakeServiceBusEventHandler,
    )
    monkeypatch.setattr(
        "services.coding_worker.app.services.progress_publisher.publish_progress",
        lambda _run_id, event: published.append(event),
    )

    job = job_handler.CodingJobMessage(
        patient_id="p2",
        mode="extract_patient",
        dry_run=True,
    )
    raw_message = Message(
        body={
            "event_type": "encounter-created",
            "patient_id": "p2",
            "plan_definition_id": "pd-gp-encounter-coding",
        },
        correlation_id="run-456",
    )
    await job_handler._run_coding_job(job, raw_message)

    encounter_ids = [c.get("encounter_id") for c in _FakeServiceBusEventHandler.calls]
    assert encounter_ids == ["e1", "e2"]
    assert any(e.get("type") == "encounter_completed" for e in published)
    assert any(e.get("type") == "run_completed" for e in published)
    assert fake_driver.closed is True


@pytest.mark.asyncio
async def test_extract_encounter_requires_encounter_id(monkeypatch):
    _FakeServiceBusEventHandler.calls = []
    fake_driver = _FakeAsyncDriver()

    monkeypatch.setattr(
        "libs.neo4j_client.client.get_async_driver",
        lambda: fake_driver,
    )
    monkeypatch.setitem(
        sys.modules,
        "libs.workflow.engine",
        types.SimpleNamespace(WorkflowEngine=_FakeWorkflowEngine),
    )
    monkeypatch.setattr(
        "libs.workflow.events.ServiceBusEventHandler",
        _FakeServiceBusEventHandler,
    )

    job = job_handler.CodingJobMessage(
        patient_id="p3",
        mode="extract_encounter",
        encounter_id=None,
    )
    raw_message = Message(body={"patient_id": "p3", "mode": "extract_encounter"})
    await job_handler._run_coding_job(job, raw_message)
    assert _FakeServiceBusEventHandler.calls == []
    assert fake_driver.closed is True
