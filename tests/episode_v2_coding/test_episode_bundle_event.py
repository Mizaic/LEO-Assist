"""Tests for the episode_bundle workflow event in the coding worker.

Atlas trace:
  DI: DI-E8FE404D
"""

from __future__ import annotations

import pytest

from services.coding_worker.app.services.job_handler import (
    CodingJobMessage,
    _dispatch_durable_for_episode_bundle,
)


def test_coding_job_message_accepts_episode_bundle_mode():
    job = CodingJobMessage.model_validate(
        {
            "patient_id": "p-1",
            "episode_id": "ep-1",
            "encounter_ids": ["e-1", "e-2"],
            "episode_context": {"suspected_site": "breast"},
            "mode": "episode_bundle",
        }
    )
    assert job.mode == "episode_bundle"
    assert job.episode_id == "ep-1"
    assert job.encounter_ids == ["e-1", "e-2"]
    assert job.episode_context == {"suspected_site": "breast"}


def test_invalid_episode_id_rejected():
    with pytest.raises(Exception):
        CodingJobMessage.model_validate(
            {
                "patient_id": "p-1",
                "episode_id": "bad id with spaces",
                "mode": "episode_bundle",
            }
        )


def test_invalid_encounter_id_in_list_rejected():
    with pytest.raises(Exception):
        CodingJobMessage.model_validate(
            {
                "patient_id": "p-1",
                "episode_id": "ep-1",
                "encounter_ids": ["e-1", "bad enc!"],
                "mode": "episode_bundle",
            }
        )


class _FakeBus:
    def __init__(self):
        self.start_calls: list[dict] = []

    async def close(self):
        return


@pytest.mark.asyncio
async def test_dispatch_episode_bundle_publishes_single_event(monkeypatch):
    fake_bus = _FakeBus()

    async def _fake_start(body, *, bus, queue_name):
        fake_bus.start_calls.append(
            {"body": body, "bus": bus, "queue_name": queue_name}
        )

    monkeypatch.setattr(
        "libs.workflow.durable_step_runner.DurableStepRunner.start",
        _fake_start,
    )

    await _dispatch_durable_for_episode_bundle(
        fake_bus,
        base_body={"plan_definition_id": "pd-episode-bundle-coding"},
        patient_id="p-1",
        episode_id="ep-1",
        encounter_ids=["e-1", "e-2"],
        episode_context={"suspected_site": "breast", "intent": "confirmed"},
        run_id="run-abc",
        dry_run=True,
        trigger_analysis=False,
    )

    assert len(fake_bus.start_calls) == 1
    body = fake_bus.start_calls[0]["body"]
    assert body["event_type"] == "episode_bundle"
    assert body["patient_id"] == "p-1"
    assert body["run_id"] == "run-abc"
    assert body["context"]["episode_id"] == "ep-1"
    assert body["context"]["encounter_ids"] == ["e-1", "e-2"]
    assert body["context"]["episode_context"]["suspected_site"] == "breast"
    assert body["context"]["mode"] == "episode_bundle"
    assert body["context"]["dry_run"] is True
    assert fake_bus.start_calls[0]["queue_name"] == "pipeline-jobs"
