"""Tests for patient document chunk pipeline re-runs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.patient_document_runs.service import (
    DocumentRunError,
    resolve_document_run_context,
    start_document_run,
)
from libs.sbar.trigger_chunk_scope import TriggerChunkScopeResult


def test_resolve_document_run_context_requires_referral():
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "p1",
            "tenant_id": "tenant-a",
            "document_reference_id": "dr1",
            "referral_id": "",
            "encounter_id": "",
        }
    ]
    with pytest.raises(DocumentRunError, match="not linked to a referral"):
        resolve_document_run_context(
            client, patient_id="p1", document_reference_id="dr1"
        )


def test_resolve_document_run_context_uses_service_provider_org_when_tenant_missing():
    client = MagicMock()
    client.run.side_effect = [
        [
            {
                "patient_id": "9728344007",
                "tenant_id": "M0L1I",
                "document_reference_id": "DocumentReference-151066",
                "referral_id": "000049823847",
                "encounter_id": "000049823847:referral-assessment",
            }
        ],
        [{"encounter_id": "000049823847:referral-assessment"}],
    ]
    ctx = resolve_document_run_context(
        client,
        patient_id="9728344007",
        document_reference_id="DocumentReference-151066",
    )
    assert ctx.tenant_id == "M0L1I"
    assert ctx.referral_id == "000049823847"
    assert ctx.encounter_id == "000049823847:referral-assessment"
    assert client.run.call_count == 2


def test_start_document_run_publishes_referral_received():
    client = MagicMock()
    client.run.side_effect = [
        [
            {
                "patient_id": "p1",
                "tenant_id": "tenant-a",
                "document_reference_id": "dr1",
                "referral_id": "rr1",
                "encounter_id": "rr1:referral-assessment",
            }
        ],
        [{"encounter_id": "rr1:referral-assessment"}],
    ]
    published: list[tuple[dict, str]] = []

    def _publish(body, run_id):
        published.append((body, run_id))

    with patch(
        "libs.patient_document_runs.service.validate_trigger_chunk_scope",
        return_value=TriggerChunkScopeResult(
            ok=True,
            ordered_chunk_ids=["c1", "c2"],
        ),
    ), patch(
        "libs.patient_document_runs.service.poll_run_status",
        return_value={"status": "queued", "assessment_id": ""},
    ), patch(
        "libs.patient_document_runs.service.list_stage_progress",
        return_value=[],
    ), patch(
        "libs.patient_document_runs.service.bootstrap_durable_lab_run",
        return_value=None,
    ):
        result = start_document_run(
            client,
            patient_id="p1",
            document_reference_id="dr1",
            chunk_ids=["c1", "c2"],
            publish=_publish,
        )

    assert result.status == "queued"
    assert len(published) == 1
    body, run_id = published[0]
    assert body["event_type"] == "referral-received"
    assert body["patient_id"] == "p1"
    assert body["referral_id"] == "rr1"
    assert body["document_reference_id"] == "dr1"
    assert body["chunk_ids"] == ["c1", "c2"]
    assert body["tenant_id"] == "tenant-a"
    assert body["context"]["source"] == "patient-viewer"
    assert run_id == result.run_id


def test_start_document_run_rejects_empty_chunk_ids():
    client = MagicMock()
    with pytest.raises(DocumentRunError, match="Select at least one chunk"):
        start_document_run(
            client,
            patient_id="p1",
            document_reference_id="dr1",
            chunk_ids=[],
        )
