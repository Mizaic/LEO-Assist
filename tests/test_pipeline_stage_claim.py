"""Unit tests for durable PipelineStageRun claim (DI-36F80B95 / VT)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.cypher.pipeline_stage_queries import COMPLETE_PIPELINE_STAGE_RUN
from libs.workflow.durable_steps import StepRequest, StepResult
from libs.workflow.pipeline_stage_store import PipelineStageStore, stage_run_id
from libs.workflow.stage_lease import resolve_lease_owner


def _request() -> StepRequest:
    return StepRequest(
        event_type="extraction",
        run_id="run-1",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-1",
    )


def test_claim_stage_maps_claimed_outcome() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "outcome": "claimed",
            "output_json": None,
            "next_action_ids_json": None,
            "next_published": False,
        }
    ]
    store = PipelineStageStore(client)
    result = store.claim_stage(_request(), {"patient_id": "p-1"}, lease_owner="w1")
    assert result.outcome == "claimed"
    assert client.run.call_args.kwargs["lease_owner"] == "w1"
    assert client.run.call_args.kwargs["stage_run_id"] == stage_run_id(
        "run-1", "act-ref-extract"
    )


def test_claim_stage_maps_already_completed_with_next_ids() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "outcome": "already_completed",
            "output_json": '{"entities": []}',
            "next_action_ids_json": '["act-next"]',
            "next_published": False,
        }
    ]
    store = PipelineStageStore(client)
    result = store.claim_stage(_request(), {})
    assert result.outcome == "already_completed"
    assert result.next_action_ids == ["act-next"]
    assert result.next_published is False
    assert result.output == {"entities": []}


def test_claim_stage_unknown_outcome_becomes_busy() -> None:
    client = MagicMock()
    client.run.return_value = [{"outcome": "weird"}]
    store = PipelineStageStore(client)
    result = store.claim_stage(_request(), {})
    assert result.outcome == "busy"


def test_complete_stage_persists_next_action_ids() -> None:
    client = MagicMock()
    client.run.return_value = [{"outcome": "completed"}]
    store = PipelineStageStore(client)
    store.complete_stage(
        _request(),
        StepResult(status="completed", output={"ok": True}),
        next_action_ids=["act-next"],
        next_published=False,
        lease_owner="worker-a",
        lease_generation=2,
    )
    kwargs = client.run.call_args.kwargs
    assert kwargs["next_action_ids_json"] == '["act-next"]'
    assert kwargs["next_published"] is False
    assert kwargs["lease_owner"] == "worker-a"
    assert kwargs["lease_generation"] == 2
    # DI-36F80B95: complete Cypher must stamp completed_by from lease_owner.
    assert "s.completed_by = $lease_owner" in COMPLETE_PIPELINE_STAGE_RUN
    assert "s.lease_owner = null" in COMPLETE_PIPELINE_STAGE_RUN


def test_resolve_lease_owner_prefers_aca_replica_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIPELINE_WORKER_NAME", raising=False)
    monkeypatch.setenv("CONTAINER_APP_REPLICA_NAME", "pipeline-worker--abc123")
    monkeypatch.delenv("HOSTNAME", raising=False)
    owner = resolve_lease_owner({"_message_id": "msg-9"})
    assert owner == "pipeline-worker--abc123:msg-9"


def test_resolve_lease_owner_prefers_pipeline_worker_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_WORKER_NAME", "Ada")
    monkeypatch.setenv("CONTAINER_APP_REPLICA_NAME", "pipeline-worker--abc123")
    monkeypatch.setenv("HOSTNAME", "worker")
    owner = resolve_lease_owner({"_message_id": "msg-9"})
    assert owner == "Ada:msg-9"


def test_complete_stage_maps_stale_lease() -> None:
    client = MagicMock()
    client.run.return_value = [{"outcome": "stale_lease"}]
    store = PipelineStageStore(client)
    result = store.complete_stage(
        _request(),
        StepResult(status="completed", output={"ok": True}),
        lease_owner="worker-a",
        lease_generation=1,
    )
    assert result.outcome == "stale_lease"


def test_mark_next_published_targets_stage_run_id() -> None:
    client = MagicMock()
    store = PipelineStageStore(client)
    store.mark_next_published(_request())
    assert client.run.call_args.kwargs["stage_run_id"] == "run-1:act-ref-extract"
