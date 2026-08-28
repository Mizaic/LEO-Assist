"""Tests for communication_thread step state loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline.communication_thread_loader import COMMUNICATION_THREAD_MODE
from libs.workflow.durable_steps import StepRequest
from libs.workflow.step_state_loader import (
    REFERRAL_HANDOFF_KEYS,
    apply_referral_handoff_fields,
    default_source_fields,
    load_step_state,
)


def test_referral_handoff_includes_communication_request_id() -> None:
    assert "communication_request_id" in REFERRAL_HANDOFF_KEYS
    assert "ubrn" in REFERRAL_HANDOFF_KEYS


def test_apply_referral_handoff_fields_promotes_ag_fields() -> None:
    state: dict = {}
    body = {
        "communication_request_id": "cr-1",
        "ubrn": "UBRN123",
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        "context": {"patient_id": "p1"},
    }
    request = StepRequest.from_message(
        {
            "event_type": "extraction_requested",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "plan_definition_id": "pd-referral-assessment",
            "step_id": "durable-ref-extraction",
            "patient_id": "p1",
            "encounter_id": "UBRN123:ag-assessment",
            "context": {},
        }
    )
    apply_referral_handoff_fields(state, request, body)
    assert state["communication_request_id"] == "cr-1"
    assert state["ubrn"] == "UBRN123"
    assert state["text_segmentation_mode"] == COMMUNICATION_THREAD_MODE


def test_default_source_fields_communication_thread() -> None:
    request = StepRequest.from_message(
        {
            "event_type": "extraction_requested",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "plan_definition_id": "pd-referral-assessment",
            "step_id": "durable-ref-extraction",
            "patient_id": "p1",
            "encounter_id": "UBRN123:ag-assessment",
        }
    )
    state = {
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        "communication_request_id": "cr-1",
    }
    source_type, source_id, text_property = default_source_fields(request, state)
    assert source_type == "CommunicationRequest"
    assert source_id == "cr-1"
    assert text_property == "note"


def test_enrich_loads_communication_thread_when_mode_set() -> None:
    body = {
        "event_type": "extraction_requested",
        "run_id": "run-1",
        "plan_definition_id": "pd-referral-assessment",
        "workflow_id": "pd-referral-assessment",
        "step_id": "durable-ref-extraction",
        "patient_id": "p1",
        "encounter_id": "UBRN123:ag-assessment",
        "communication_request_id": "cr-1",
        "ubrn": "UBRN123",
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
    }
    request = StepRequest.from_message(body)
    client = MagicMock()
    client.run.side_effect = [
        [{"birth_date": "1980-01-01", "gender": "female"}],
        [{"org_id": "org-1"}],
        # Receiving service lookup: an Ask-LEO thread hangs off the same
        # CommunicationRequest, so the step resolves the service it was
        # sent to before loading the thread.
        [
            {
                "id": "svc-1",
                "name": "Gynaecology 2WW",
                "ers_service_id": "ers-1",
                "specialty": "gynaecology",
                "guideline_ids_prop": None,
                "guidance_ids": [],
                "organization_id": "org-1",
                "organization_name": "Sherwood Forest Hospitals",
            }
        ],
    ]
    store = MagicMock()
    store.load_accumulated_state.return_value = {}

    loaded_state = {
        "sentences": [
            {
                "sentence_id": "c1",
                "text": "[REQUESTER] Question",
                "persist_source_label": "Communication",
            }
        ],
        "encounter_text": "[REQUESTER] Question",
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
    }
    with patch(
        "libs.workflow.step_state_loader.load_communication_thread_from_neo4j",
        return_value=loaded_state,
    ) as load_mock:
        state = load_step_state(client, store, request, body=body)

    load_mock.assert_called_once_with(client, "cr-1", chunk_ids=None)
    assert state["sentences"][0]["sentence_id"] == "c1"
    assert state["source_node_type"] == "CommunicationRequest"
