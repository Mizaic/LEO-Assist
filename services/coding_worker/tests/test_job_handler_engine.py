from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from libs.message_bus.base import Message
from services.coding_worker.app.services import job_handler


class _FakePatientGraphClient:
    rows: list[dict] = []

    def run(self, _query: str, **_kwargs):
        return list(self.rows)

    def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_extract_encounter_routes_through_durable_runner(monkeypatch):
    published: list[dict] = []
    start_calls: list[dict] = []
    mock_bus = AsyncMock()
    mock_bus.close = AsyncMock()

    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: mock_bus,
    )
    monkeypatch.setattr(
        "services.coding_worker.app.services.progress_publisher.publish_progress",
        lambda _run_id, event: published.append(event),
    )

    async def _fake_start(body, *, bus, queue_name):
        start_calls.append({"body": body, "bus": bus, "queue_name": queue_name})

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
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

    assert len(start_calls) == 1
    body = start_calls[0]["body"]
    assert body["event_type"] == "encounter-created"
    assert body["encounter_id"] == "e1"
    assert body["plan_definition_id"] == "pd-gp-encounter-coding"
    assert "encounter_text" not in (body.get("context") or {})
    assert body["context"]["trigger_analysis"] is False
    assert start_calls[0]["queue_name"] == "pipeline-jobs"
    mock_bus.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_patient_fans_out_per_encounter(monkeypatch):
    published: list[dict] = []
    start_calls: list[dict] = []
    mock_bus = AsyncMock()
    mock_bus.close = AsyncMock()

    fake_pg = _FakePatientGraphClient()
    fake_pg.rows = [
        {"encounter_id": "e1"},
        {"encounter_id": ""},
        {"encounter_id": "e2"},
    ]

    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: mock_bus,
    )
    monkeypatch.setattr(
        "libs.neo4j_client.client.PatientGraphClient",
        lambda: fake_pg,
    )
    monkeypatch.setattr(
        "services.coding_worker.app.services.progress_publisher.publish_progress",
        lambda _run_id, event: published.append(event),
    )

    async def _fake_start(body, *, bus, queue_name):
        start_calls.append(body)

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
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

    encounter_ids = [call.get("encounter_id") for call in start_calls]
    assert encounter_ids == ["e1", "e2"]
    assert all(call["context"]["trigger_analysis"] is False for call in start_calls)
    assert any(e.get("type") == "run_completed" for e in published)
    mock_bus.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_encounter_requires_encounter_id(monkeypatch):
    start_calls: list[dict] = []
    mock_bus = AsyncMock()
    mock_bus.close = AsyncMock()

    monkeypatch.setattr(
        "libs.message_bus.factory.create_message_bus",
        lambda: mock_bus,
    )

    async def _fake_start(body, *, bus, queue_name):
        start_calls.append(body)

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
    )

    job = job_handler.CodingJobMessage(
        patient_id="p3",
        mode="extract_encounter",
        encounter_id=None,
    )
    raw_message = Message(body={"patient_id": "p3", "mode": "extract_encounter"})
    await job_handler._run_coding_job(job, raw_message)
    assert start_calls == []
    mock_bus.close.assert_awaited_once()
