"""Tests for the episode_bundle workflow event in the coding worker.

Atlas trace:
  DI: DI-E8FE404D
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.message_bus.base import Message
from services.coding_worker.app.services.job_handler import (
    CodingJobMessage,
    _dispatch_engine_for_episode_bundle,
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


class _FakeHandler:
    def __init__(self):
        self.messages: list[Message] = []

    async def handle_message(self, message: Message, *, step_callback=None):
        self.messages.append(message)
        return {"status": "ok"}


@pytest.mark.asyncio
async def test_dispatch_episode_bundle_publishes_single_event():
    handler = _FakeHandler()

    callbacks: list[dict[str, Any]] = []

    def _cb(payload: dict[str, Any]) -> None:
        callbacks.append(payload)

    await _dispatch_engine_for_episode_bundle(
        handler,
        _cb,
        base_body={"plan_definition_id": "pd-episode-bundle-coding"},
        patient_id="p-1",
        episode_id="ep-1",
        encounter_ids=["e-1", "e-2"],
        episode_context={"suspected_site": "breast", "intent": "confirmed"},
        run_id="run-abc",
        dry_run=True,
        trigger_analysis=False,
    )

    assert len(handler.messages) == 1
    msg = handler.messages[0]
    body = msg.body
    assert body["event_type"] == "episode_bundle"
    assert body["patient_id"] == "p-1"
    assert body["context"]["episode_id"] == "ep-1"
    assert body["context"]["encounter_ids"] == ["e-1", "e-2"]
    assert body["context"]["episode_context"]["suspected_site"] == "breast"
    assert body["context"]["mode"] == "episode_bundle"
    assert body["context"]["dry_run"] is True
    assert msg.correlation_id == "run-abc"
    assert msg.subject == "episode-bundle"
