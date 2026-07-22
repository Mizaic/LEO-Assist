"""VT-E4457D16 -- competing subscribers + claim single-flight.

Two in-process consumers share one InMemoryQueueAdapter queue. Duplicate
deliveries of the same durable stage execute work exactly once.
SettlementTrackingBus mirrors Azure complete vs abandon for defer paths.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from libs.message_bus.base import Message
from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter
from libs.message_bus.settlement import MessageDeferError
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_stage_store import PipelineStageStore
from libs.workflow.stage_lease import StageLeaseBusyError
from tests.helpers.claim_race_client import InMemoryClaimClient
from tests.helpers.settlement_bus import SettlementTrackingBus

_QUEUE = "pipeline-jobs"


def _stage_body(run_id: str = "run-compete-1") -> dict[str, Any]:
    return {
        "event_type": "extraction",
        "run_id": run_id,
        "workflow_id": "pd-referral-assessment",
        "plan_definition_id": "pd-referral-assessment",
        "step_id": "act-ref-extract",
        "patient_id": "p-compete-1",
    }


@pytest.mark.asyncio
async def test_duplicate_delivery_two_subscribers_executes_once() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    bus = InMemoryQueueAdapter()
    executions: list[str] = []
    started = asyncio.Event()

    async def handler(msg: Message) -> None:
        request = StepRequest.from_message(msg.body)
        store.ensure_schema()
        store.upsert_run(request, status="running")
        claim = store.claim_stage(
            request,
            {"patient_id": request.patient_id},
            lease_owner=msg.message_id,
            lease_seconds=3600,
        )
        if claim.outcome != "claimed":
            return
        executions.append(msg.message_id)
        # Hold the lease briefly so a racing second delivery sees busy.
        await asyncio.sleep(0.05)
        store.complete_stage(
            request,
            StepResult(status="completed", output={"ok": True}),
            lease_owner=claim.lease_owner,
            lease_generation=claim.lease_generation,
        )
        started.set()

    await bus.subscribe(_QUEUE, handler)
    await bus.subscribe(_QUEUE, handler)

    body = _stage_body()
    await bus.send(_QUEUE, Message(body=body))
    await bus.send(_QUEUE, Message(body=body))

    await asyncio.wait_for(started.wait(), timeout=2.0)
    await asyncio.sleep(0.1)
    await bus.close()

    assert len(executions) == 1


@pytest.mark.asyncio
async def test_distinct_stages_drain_across_two_subscribers() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    bus = InMemoryQueueAdapter()
    executions: list[str] = []
    done = asyncio.Event()

    async def handler(msg: Message) -> None:
        request = StepRequest.from_message(msg.body)
        store.upsert_run(request, status="running")
        claim = store.claim_stage(
            request, {}, lease_owner=msg.message_id, lease_seconds=3600
        )
        if claim.outcome != "claimed":
            return
        executions.append(request.run_id)
        store.complete_stage(
            request,
            StepResult(status="completed", output={"ok": True}),
            lease_owner=claim.lease_owner,
            lease_generation=claim.lease_generation,
        )
        if len(executions) >= 5:
            done.set()

    await bus.subscribe(_QUEUE, handler)
    await bus.subscribe(_QUEUE, handler)

    for i in range(5):
        await bus.send(_QUEUE, Message(body=_stage_body(run_id=f"run-drain-{i}")))

    await asyncio.wait_for(done.wait(), timeout=2.0)
    await bus.close()

    assert sorted(executions) == [f"run-drain-{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_already_completed_second_delivery_skips_work() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    bus = InMemoryQueueAdapter()
    executions: list[str] = []

    async def handler(msg: Message) -> None:
        request = StepRequest.from_message(msg.body)
        store.upsert_run(request, status="running")
        claim = store.claim_stage(
            request, {}, lease_owner=msg.message_id, lease_seconds=3600
        )
        if claim.outcome == "claimed":
            executions.append("claimed")
            store.complete_stage(
                request,
                StepResult(status="completed", output={"ok": True}),
                lease_owner=claim.lease_owner,
                lease_generation=claim.lease_generation,
            )
            return
        if claim.outcome == "already_completed":
            executions.append("already_completed")
            return
        executions.append(claim.outcome)

    await bus.subscribe(_QUEUE, handler)

    body = _stage_body("run-done-once")
    await bus.send(_QUEUE, Message(body=body))
    await asyncio.sleep(0.05)
    await bus.send(_QUEUE, Message(body=body))
    await asyncio.sleep(0.1)
    await bus.close()

    assert executions == ["claimed", "already_completed"]


@pytest.mark.asyncio
async def test_busy_defer_abandons_message_not_complete() -> None:
    """Stage lease busy must abandon (defer) the Service Bus message."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    bus = SettlementTrackingBus()
    body = _stage_body("run-busy-settle")
    request = StepRequest.from_message(body)
    store.ensure_schema()
    store.upsert_run(request, status="running")
    store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)

    async def handler(msg: Message) -> None:
        claim = store.claim_stage(
            request,
            {},
            lease_owner=msg.message_id,
            lease_seconds=3600,
        )
        if claim.outcome == "busy":
            raise StageLeaseBusyError(
                "stage busy",
                action_id=request.step_id,
                run_id=request.run_id,
            )
        if claim.outcome == "claimed":
            store.complete_stage(
                request,
                StepResult(status="completed", output={"ok": True}),
                lease_owner=claim.lease_owner,
                lease_generation=claim.lease_generation,
            )

    await bus.subscribe(_QUEUE, handler)
    await bus.send(_QUEUE, Message(body=body, message_id="msg-busy-1"))
    await asyncio.sleep(0.1)
    await bus.close()

    assert bus.settlement.abandoned == ["msg-busy-1"]
    assert bus.settlement.completed == []


@pytest.mark.asyncio
async def test_stale_complete_recovered_completes_message() -> None:
    """Idempotent already_completed after stale complete completes the message."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    bus = SettlementTrackingBus()
    body = _stage_body("run-stale-recover")
    request = StepRequest.from_message(body)
    store.ensure_schema()
    store.upsert_run(request, status="running")

    async def handler(msg: Message) -> None:
        claim = store.claim_stage(
            request,
            {},
            lease_owner=msg.message_id,
            lease_seconds=3600,
        )
        if claim.outcome == "claimed":
            store.complete_stage(
                request,
                StepResult(status="completed", output={"entities": []}),
                lease_owner=claim.lease_owner,
                lease_generation=claim.lease_generation,
            )
            return
        if claim.outcome == "already_completed":
            return

    await bus.subscribe(_QUEUE, handler)
    await bus.send(_QUEUE, Message(body=body, message_id="msg-recover-1"))
    await bus.send(_QUEUE, Message(body=body, message_id="msg-recover-2"))
    await asyncio.sleep(0.15)
    await bus.close()

    assert sorted(bus.settlement.completed) == ["msg-recover-1", "msg-recover-2"]
    assert bus.settlement.abandoned == []


@pytest.mark.asyncio
async def test_two_workers_same_step_single_clinical_write() -> None:
    """Competing deliveries produce one persisted clinical output."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    bus = SettlementTrackingBus()
    body = _stage_body("run-single-write")
    request = StepRequest.from_message(body)
    store.ensure_schema()
    store.upsert_run(request, status="running")
    clinical_writes: list[dict[str, Any]] = []

    async def handler(msg: Message) -> None:
        claim = store.claim_stage(
            request,
            {},
            lease_owner=msg.message_id,
            lease_seconds=3600,
        )
        if claim.outcome == "busy":
            raise StageLeaseBusyError(
                "stage busy",
                action_id=request.step_id,
                run_id=request.run_id,
            )
        if claim.outcome != "claimed":
            return
        await asyncio.sleep(0.02)
        clinical_writes.append({"documents_written": 1})
        store.complete_stage(
            request,
            StepResult(status="completed", output=clinical_writes[-1]),
            lease_owner=claim.lease_owner,
            lease_generation=claim.lease_generation,
        )

    await bus.subscribe(_QUEUE, handler)
    await bus.subscribe(_QUEUE, handler)
    await bus.send(_QUEUE, Message(body=body, message_id="dup-a"))
    await bus.send(_QUEUE, Message(body=body, message_id="dup-b"))
    await asyncio.sleep(0.2)
    await bus.close()

    assert len(clinical_writes) == 1
    assert len(bus.settlement.completed) == 1
    assert len(bus.settlement.abandoned) == 1
