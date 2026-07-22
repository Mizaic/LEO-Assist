"""Gate 5 G5.6 -- crash and lease-expiry chaos at unit/integration level."""

from __future__ import annotations

import pytest

from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from tests.helpers.claim_race_client import InMemoryClaimClient


def _persist_request(run_id: str = "run-persist-1") -> StepRequest:
    return StepRequest(
        event_type="persist",
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        step_id="act-ref-persist",
        patient_id="p-persist-1",
        plan_definition_id="pd-referral-assessment",
    )


def _request(run_id: str = "run-chaos-1") -> StepRequest:
    return StepRequest(
        event_type="extraction",
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-chaos-1",
        plan_definition_id="pd-referral-assessment",
    )


def test_crash_after_claim_allows_reclaim_and_rejects_stale_complete() -> None:
    """Worker A crashes; worker B reclaims; A stale completion is rejected."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request()
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)

    worker_a = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=60)
    assert worker_a.outcome == "claimed"

    client.expire_lease(stage_id)
    worker_b = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=60)
    assert worker_b.outcome == "claimed"
    assert worker_b.lease_generation == 2

    stale = store.complete_stage(
        request,
        StepResult(status="completed", output={"from": "crashed-a"}),
        lease_owner=worker_a.lease_owner,
        lease_generation=worker_a.lease_generation,
    )
    assert stale.outcome == "stale_lease"

    fresh = store.complete_stage(
        request,
        StepResult(status="completed", output={"from": "worker-b"}),
        lease_owner=worker_b.lease_owner,
        lease_generation=worker_b.lease_generation,
    )
    assert fresh.outcome == "completed"
    assert client.stages[stage_id]["output_json"] is not None


def test_lease_renewal_failure_leaves_stage_reclaimable() -> None:
    """When heartbeat renewal fails, another worker can reclaim after expiry."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-renew-fail")
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)

    first = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=30)
    renewed = store.renew_stage_lease(
        request,
        lease_owner=first.lease_owner,
        lease_generation=first.lease_generation,
        lease_seconds=30,
    )
    assert renewed is True

    client.expire_lease(stage_id)

    second = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=30)
    assert second.outcome == "claimed"
    assert second.lease_generation == 2


def test_completed_stage_replay_does_not_mutate_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay claim after completion returns stored output without incrementing."""
    monkeypatch.setenv("PIPELINE_STAGE_MAX_ATTEMPTS", "5")
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-replay-stable")
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)

    claim = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    output = {"entities": [{"concept_id": "123"}]}
    store.complete_stage(
        request,
        StepResult(status="completed", output=output),
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )
    stored_output = client.stages[stage_id]["output_json"]

    replay = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)
    assert replay.outcome == "already_completed"
    assert client.stages[stage_id]["output_json"] == stored_output
    assert client.stages[stage_id]["attempt"] == 1


def test_poison_after_max_reclaims_blocks_further_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_STAGE_MAX_ATTEMPTS", "2")
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-poison-chaos")
    store.upsert_run(request, status="running")
    stage_id = stage_run_id(request.run_id, request.step_id)

    store.claim_stage(request, {}, lease_owner="w1", lease_seconds=10)
    client.expire_lease(stage_id)
    store.claim_stage(request, {}, lease_owner="w2", lease_seconds=10)
    client.expire_lease(stage_id)

    poison = store.claim_stage(request, {}, lease_owner="w3", lease_seconds=10)
    assert poison.outcome == "poisoned"
    assert client.runs[request.run_id]["status"] == "poisoned"


def test_persist_stale_complete_reclaim_is_already_completed() -> None:
    """Duplicate persist finish: stale complete can replay as already_completed."""
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _persist_request("run-persist-stale")
    store.upsert_run(request, status="running")
    owner = "Curie:msg-persist-1"

    claim = store.claim_stage(request, {}, lease_owner=owner, lease_seconds=3600)
    assert claim.outcome == "claimed"
    assert claim.lease_generation == 1

    output = {"documents_written": 2}
    store.complete_stage(
        request,
        StepResult(status="completed", output=output),
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )

    stale = store.complete_stage(
        request,
        StepResult(status="completed", output=output),
        lease_owner=claim.lease_owner,
        lease_generation=claim.lease_generation,
    )
    assert stale.outcome == "stale_lease"

    replay = store.claim_stage(request, {}, lease_owner=owner, lease_seconds=3600)
    assert replay.outcome == "already_completed"
    assert replay.output == output


def test_stale_complete_recovered_settlement_is_complete() -> None:
    """After stale complete, replay already_completed completes the SB message."""
    from libs.message_bus.settlement import resolve_durable_step_settlement
    from libs.workflow.durable_steps import StepResult

    result = StepResult(
        status="completed",
        output={"documents_written": 2},
        warnings=["already_completed"],
    )
    assert resolve_durable_step_settlement(result) == "complete"


def test_stale_complete_without_recovery_settlement_is_abandon() -> None:
    """Unrecovered stale lease must defer (abandon), not complete."""
    from libs.message_bus.settlement import (
        MessageDeferError,
        enforce_durable_step_settlement,
        resolve_durable_step_settlement,
    )
    from libs.workflow.durable_steps import StepResult

    skipped = StepResult(status="skipped", warnings=["stale_lease"])
    assert resolve_durable_step_settlement(skipped) == "abandon"

    with pytest.raises(MessageDeferError, match="stale_lease"):
        enforce_durable_step_settlement(
            skipped,
            message_id="msg-stale",
            run_id="run-stale",
            action_id="act-ref-persist",
        )
