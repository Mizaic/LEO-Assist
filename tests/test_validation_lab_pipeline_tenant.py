"""Tests for Validation Lab pipeline tenant + chunk loading fixes."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.validation_lab.pipeline import build_pipeline_message
from libs.validation_lab.tenant import VALIDATION_LAB_TENANT_ID
from libs.workflow.durable_steps import StepRequest
from libs.workflow.step_state_loader import load_document_chunks_into_state


def test_build_pipeline_message_sets_validation_lab_tenant() -> None:
    body = build_pipeline_message(
        {
            "id": "case-1",
            "patient_id": "lab-case-1:patient",
            "encounter_id": "lab-case-1:encounter",
            "referral_id": "lab-case-1:referral",
            "document_reference_id": "lab-case-1:document",
            "chunk_ids": ["chunk-1"],
        },
        run_id="run-1",
        plan_id="pd-referral-assessment",
        dry_run=False,
    )
    assert body["tenant_id"] == VALIDATION_LAB_TENANT_ID
    assert body["context"]["source"] == "validation-lab"


def _lab_request() -> StepRequest:
    return StepRequest.from_message(
        {
            "event_type": "extraction_requested",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "plan_definition_id": "pd-referral-assessment",
            "step_id": "act-ref-extract",
            "patient_id": "lab-case-1:patient",
            "encounter_id": "lab-case-1:encounter",
            "context": {"source": "validation-lab"},
        }
    )


def _lab_state() -> dict:
    return {
        "chunk_ids": ["chunk-1"],
        "text_segmentation_mode": "document_chunks",
        "context": {"source": "validation-lab"},
    }


def _stub_chunk_loader(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.workflow.step_state_loader.load_document_chunks_from_neo4j",
        lambda _client, chunk_ids, **_scope: {
            "sentences": [
                {
                    "sentence_id": chunk_ids[0],
                    "text": "Dysphagia",
                    "start": 0,
                    "end": 9,
                }
            ],
            "encounter_text": "Dysphagia",
            "text_segmentation_mode": "document_chunks",
        },
    )


def test_validation_lab_runs_trigger_chunk_scope(monkeypatch) -> None:
    """One pipeline: the Lab is checked for chunk scope exactly like BAU.

    The Lab used to be exempt, so production had a failure mode the Lab
    could never reproduce. The Lab's fixture graph satisfies the real
    query, so the check passes on its own merits and chunks still load.
    """
    _stub_chunk_loader(monkeypatch)
    scope_called = {"value": False}

    def _scope(*_args, **_kwargs):
        scope_called["value"] = True
        return []

    monkeypatch.setattr(
        "libs.workflow.step_state_loader._validate_trigger_chunk_scope",
        _scope,
    )
    state = _lab_state()
    load_document_chunks_into_state(MagicMock(), state, _lab_request())
    assert scope_called["value"] is True
    assert state.get("sentences")
    assert not state.get("errors")
    assert not state.get("chunk_scope_failed")


def test_validation_lab_stops_on_chunk_scope_failure(monkeypatch) -> None:
    """A failing scope check must stop the Lab, as it stops production."""
    _stub_chunk_loader(monkeypatch)
    monkeypatch.setattr(
        "libs.workflow.step_state_loader._validate_trigger_chunk_scope",
        lambda *_args, **_kwargs: ["chunk out of scope"],
    )
    state = _lab_state()
    load_document_chunks_into_state(MagicMock(), state, _lab_request())
    assert state.get("chunk_scope_failed") is True
    assert state.get("errors") == ["chunk out of scope"]
    assert not state.get("sentences")
