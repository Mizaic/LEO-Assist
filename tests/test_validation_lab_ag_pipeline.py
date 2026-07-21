"""Tests for Validation Lab A&G run API helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.validation_lab.ag_pipeline import (
    AgPipelineError,
    resolve_communication_request,
)
from libs.validation_lab.models import PersistMode
from libs.validation_lab.service import refresh_ag_run, start_ag_run


def test_resolve_communication_request_missing_ubrn() -> None:
    with pytest.raises(AgPipelineError, match="ubrn is required"):
        resolve_communication_request(MagicMock(), "")


def test_resolve_communication_request_not_found() -> None:
    client = MagicMock()
    client.run.return_value = []
    with pytest.raises(AgPipelineError, match="not found"):
        resolve_communication_request(client, "UBRN404")


def test_ag_run_resolves_ubrn_and_enqueues() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "communication_request_id": "cr-1",
            "patient_id": "p1",
            "ubrn": "UBRN123",
        }
    ]
    published: list[dict] = []

    def _capture(body: dict, run_id: str) -> None:
        published.append({"body": body, "run_id": run_id})

    result = start_ag_run(
        client,
        ubrn="UBRN123",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction"],
        persist_mode=PersistMode.production,
        publish=_capture,
    )
    assert result["resolved"]["communication_request_id"] == "cr-1"
    assert published
    assert published[0]["body"]["text_segmentation_mode"] == "communication_thread"
    assert published[0]["body"]["ubrn"] == "UBRN123"


def test_ag_run_poll_same_as_referral_run() -> None:
    client = MagicMock()
    with (
        patch(
            "libs.validation_lab.service.poll_run_status",
            return_value={"status": "completed", "assessment_id": "assess-1"},
        ),
        patch(
            "libs.validation_lab.service.read_real_outputs",
            return_value=MagicMock(to_dict=lambda: {"snomed_codes": ["123"]}),
        ),
    ):
        packed = refresh_ag_run(client, "run-99")
    assert packed["run"]["status"] == "completed"
    assert packed["run"]["outputs"]["snomed_codes"] == ["123"]
