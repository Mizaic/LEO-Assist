"""VT-E4457D16 -- concurrent PipelineStageRun claim single-flight.

Proves DI-36F80B95 AC: a stage claim succeeds only when the stage is not
completed and has no unexpired lease held by another worker.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from tests.helpers.claim_race_client import InMemoryClaimClient


def _request(run_id: str = "run-race-1") -> StepRequest:
    return StepRequest(
        event_type="extraction",
        run_id=run_id,
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-race-1",
        plan_definition_id="pd-referral-assessment",
    )


def test_concurrent_claims_yield_exactly_one_claimed() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request()
    store.ensure_schema()
    store.upsert_run(request, status="running")

    def _claim(owner: str) -> str:
        return store.claim_stage(
            request, {"patient_id": "p-race-1"}, lease_owner=owner, lease_seconds=3600
        ).outcome

    owners = [f"worker-{i}" for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_claim, owner) for owner in owners]
        outcomes = [f.result() for f in as_completed(futures)]

    assert outcomes.count("claimed") == 1
    assert outcomes.count("busy") == 7
    assert "already_completed" not in outcomes


def test_live_lease_blocks_other_owner() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-lease-live")
    store.upsert_run(request, status="running")

    first = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    second = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)

    assert first.outcome == "claimed"
    assert second.outcome == "busy"


def test_expired_lease_allows_reclaim_by_other_owner() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-lease-expired")
    store.upsert_run(request, status="running")

    first = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    assert first.outcome == "claimed"
    assert first.lease_generation == 1

    client.expire_lease(stage_run_id(request.run_id, request.step_id))
    second = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)
    assert second.outcome == "claimed"
    assert second.lease_generation == 2


def test_stale_owner_cannot_complete_after_reclaim() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-stale-complete")
    store.upsert_run(request, status="running")

    first = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    client.expire_lease(stage_run_id(request.run_id, request.step_id))
    second = store.claim_stage(request, {}, lease_owner="worker-b", lease_seconds=3600)

    from libs.workflow.durable_steps import StepResult

    stale = store.complete_stage(
        request,
        StepResult(status="completed", output={"from": "a"}),
        lease_owner=first.lease_owner,
        lease_generation=first.lease_generation,
    )
    assert stale.outcome == "stale_lease"

    fresh = store.complete_stage(
        request,
        StepResult(status="completed", output={"from": "b"}),
        lease_owner=second.lease_owner,
        lease_generation=second.lease_generation,
    )
    assert fresh.outcome == "completed"


def test_same_owner_can_reclaim_live_lease() -> None:
    client = InMemoryClaimClient()
    store = PipelineStageStore(client)
    request = _request("run-lease-same-owner")
    store.upsert_run(request, status="running")

    first = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    second = store.claim_stage(request, {}, lease_owner="worker-a", lease_seconds=3600)
    assert first.outcome == "claimed"
    assert second.outcome == "claimed"


@pytest.mark.integration
def test_live_neo4j_concurrent_claim_exactly_one() -> None:
    """Optional: real Cypher race against Patient Graph when credentials exist."""
    import os

    from libs.neo4j_client.client import PatientGraphClient

    if os.getenv("LIVE_NEO4J") != "1" and os.getenv("LIVE_NEO4J_GUIDANCE") != "1":
        pytest.skip("Set LIVE_NEO4J=1 to run the live claim race")
    uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_PATIENT_URI")
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PATIENT_PASSWORD")
    if not uri or not password:
        pytest.skip("Patient Graph credentials not configured")

    try:
        client = PatientGraphClient()
        client.run("RETURN 1 AS ok")
    except Exception as exc:  # noqa: BLE001 -- connectivity probe
        pytest.skip(f"Patient Graph unreachable: {exc}")

    store = PipelineStageStore(client)
    request = _request(f"run-live-race-{os.getpid()}")
    store.ensure_schema()
    store.upsert_run(request, status="running")

    def _claim(owner: str) -> str:
        return store.claim_stage(
            request, {}, lease_owner=owner, lease_seconds=120
        ).outcome

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_claim, f"w-{i}") for i in range(8)]
        outcomes = [f.result() for f in as_completed(futures)]

    assert outcomes.count("claimed") == 1
    assert outcomes.count("busy") == 7
