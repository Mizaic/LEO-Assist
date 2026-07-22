"""D1.9 -- stage reclaim attempts and terminal poison semantics."""

from __future__ import annotations

import pytest

from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from tests.helpers.claim_race_client import InMemoryClaimClient


def _request(run_id: str = "run-poison-1") -> StepRequest:
    return StepRequest(
        event_type="extraction",
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-poison-1",
        plan_definition_id="pd-referral-assessment",
    )


def test_reclaim_increments_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_STAGE_MAX_ATTEMPTS", "5")
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request()
    store.upsert_run(request, status="running")

    first = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    assert first.outcome == "claimed"
    assert client.stages[stage_run_id(request.run_id, request.step_id)]["attempt"] == 1

    client.expire_lease(stage_run_id(request.run_id, request.step_id))
    second = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)
    assert second.outcome == "claimed"
    assert client.stages[stage_run_id(request.run_id, request.step_id)]["attempt"] == 2


def test_exceeded_attempts_returns_poison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_STAGE_MAX_ATTEMPTS", "2")
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-poison-max")
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)

    store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    client.expire_lease(stage_id)
    store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)
    client.expire_lease(stage_id)

    poison = store.claim_stage(request, {}, lease_owner="worker-c", lease_seconds=3600)
    assert poison.outcome == "poisoned"
    assert client.stages[stage_id]["status"] == "poisoned"
    assert client.runs[request.run_id]["status"] == "poisoned"


def test_poisoned_stage_cannot_be_claimed_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_STAGE_MAX_ATTEMPTS", "1")
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-poison-stay")
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)

    store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    client.expire_lease(stage_id)
    poison = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)
    assert poison.outcome == "poisoned"

    again = store.claim_stage(request, {}, lease_owner="worker-c", lease_seconds=3600)
    assert again.outcome == "poisoned"
