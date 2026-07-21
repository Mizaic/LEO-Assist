"""Tests for A&G communication_thread bus message contract."""

from __future__ import annotations

import pytest

from libs.pipeline.communication_thread_loader import COMMUNICATION_THREAD_MODE
from libs.referral_simulator.message import (
    ReferralSimulatorError,
    build_communication_assessment_message,
)


def test_build_communication_assessment_message_requires_ids() -> None:
    with pytest.raises(ReferralSimulatorError, match="communication_request_id"):
        build_communication_assessment_message(
            patient_id="p1",
            communication_request_id="",
            ubrn="UBRN1",
            run_id="run-1",
        )
    with pytest.raises(ReferralSimulatorError, match="ubrn"):
        build_communication_assessment_message(
            patient_id="p1",
            communication_request_id="cr-1",
            ubrn="",
            run_id="run-1",
        )
    with pytest.raises(ReferralSimulatorError, match="patient_id"):
        build_communication_assessment_message(
            patient_id="",
            communication_request_id="cr-1",
            ubrn="UBRN1",
            run_id="run-1",
        )


def test_build_communication_assessment_message_shape() -> None:
    body = build_communication_assessment_message(
        patient_id="p1",
        communication_request_id="cr-1",
        ubrn="UBRN123",
        run_id="run-1",
        guideline_id="NG12",
        completeness_domain="cancer_referrals",
        guideline_ruleset_version="candidate-v2",
        chunk_ids=["chunk-a"],
        context={"case_id": "lab-1"},
    )
    assert body["event_type"] == "referral-received"
    assert body["plan_definition_id"] == "pd-referral-assessment"
    assert body["text_segmentation_mode"] == COMMUNICATION_THREAD_MODE
    assert body["source_node_type"] == "CommunicationRequest"
    assert body["source_node_id"] == "cr-1"
    assert body["communication_request_id"] == "cr-1"
    assert body["ubrn"] == "UBRN123"
    assert body["encounter_id"] == "UBRN123:ag-assessment"
    assert body["mode"] == "ag_assessment"
    assert body["chunk_ids"] == ["chunk-a"]
    assert body["guideline_ruleset_version"] == "candidate-v2"
    assert body["context"]["case_id"] == "lab-1"


def test_build_communication_assessment_message_allows_empty_chunk_ids() -> None:
    body = build_communication_assessment_message(
        patient_id="p1",
        communication_request_id="cr-1",
        ubrn="UBRN123",
        run_id="run-1",
    )
    assert "chunk_ids" not in body
