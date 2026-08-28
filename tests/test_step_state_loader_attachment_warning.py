"""Loader warnings reach pipeline state without erasing earlier ones.

Why this matters
----------------
``load_document_chunks_into_state`` merges what the chunk loader returns
into pipeline state. A plain ``state.update`` would overwrite a warnings
list raised by an earlier loader instead of adding to it, so a degradation
already recorded could vanish before anyone saw it
(fail-closed-boundary.mdc: a clinician must be able to tell from the output
that something happened).

The warning used here is a stand-in for any loader warning. The specific
"attachment not read" warning this file was written for no longer exists:
extraction now reads attachments, so claiming otherwise would be false. The
merge invariant it exercised is still worth holding.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.workflow.step_state_loader import StepRequest, load_document_chunks_into_state

_DROPPED = "chunk_text_empty: LEO skipped a chunk that held no readable text"


def _request() -> StepRequest:
    return StepRequest(
        event_type="extraction",
        run_id="run-1",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-1",
        plan_definition_id="pd-referral-assessment",
    )


def _load(state: dict, loaded: dict) -> None:
    with (
        patch(
            "libs.workflow.step_state_loader.load_document_chunks_from_neo4j",
            return_value=loaded,
        ),
        patch(
            "libs.workflow.step_state_loader._validate_trigger_chunk_scope",
            return_value=[],
        ),
    ):
        load_document_chunks_into_state(MagicMock(), state, _request())


def _loaded_with_dropped_attachment() -> dict:
    return {
        "sentences": [{"sentence_id": "chunk-1", "text": "x"}],
        "encounter_text": "x",
        "warnings": [_DROPPED],
    }


def test_dropped_attachment_warning_reaches_pipeline_state() -> None:
    state = {
        "chunk_ids": ["chunk-1"],
        "text_segmentation_mode": "document_chunks",
    }

    _load(state, _loaded_with_dropped_attachment())

    assert _DROPPED in (state.get("warnings") or [])


def test_dropped_attachment_warning_does_not_erase_earlier_warnings() -> None:
    state = {
        "chunk_ids": ["chunk-1"],
        "text_segmentation_mode": "document_chunks",
        "warnings": ["healthcare_service_missing"],
    }

    _load(state, _loaded_with_dropped_attachment())

    warnings = state.get("warnings") or []
    assert "healthcare_service_missing" in warnings
    assert _DROPPED in warnings


def test_chunk_load_warnings_are_not_duplicated_on_repeat_load() -> None:
    state = {
        "chunk_ids": ["chunk-1"],
        "text_segmentation_mode": "document_chunks",
        "warnings": [_DROPPED],
    }

    _load(state, _loaded_with_dropped_attachment())

    assert (state.get("warnings") or []).count(_DROPPED) == 1
