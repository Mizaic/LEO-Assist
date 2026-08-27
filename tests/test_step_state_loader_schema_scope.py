"""Org/service scope passed into document chunk loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.workflow.step_state_loader import StepRequest, load_document_chunks_into_state


def test_production_chunk_load_uses_org_service_fallbacks() -> None:
    client = MagicMock()
    state = {
        "chunk_ids": ["chunk-1"],
        "org_id": "RK5",
        "service_id": "7980224",
        "text_segmentation_mode": "document_chunks",
    }
    request = StepRequest(
        event_type="extraction",
        run_id="run-1",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-extract",
        patient_id="p-1",
        plan_definition_id="pd-referral-assessment",
    )

    with (
        patch(
            "libs.workflow.step_state_loader.load_document_chunks_from_neo4j",
            return_value={"sentences": [{"sentence_id": "chunk-1", "text": "x"}]},
        ) as mock_load,
        patch(
            "libs.workflow.step_state_loader._validate_trigger_chunk_scope",
            return_value=[],
        ),
    ):
        load_document_chunks_into_state(client, state, request)

    mock_load.assert_called_once()
    _client, chunk_ids, organization_id, service_id, ers_service_id = (
        mock_load.call_args[0][0],
        mock_load.call_args[0][1],
        mock_load.call_args[1]["organization_id"],
        mock_load.call_args[1]["service_id"],
        mock_load.call_args[1]["ers_service_id"],
    )
    assert chunk_ids == ["chunk-1"]
    assert organization_id == "RK5"
    assert service_id == "7980224"
    assert ers_service_id == ""
