"""Tests for referral-aware pipeline chunk resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.patient_document_runs.chunk_resolver import resolve_pipeline_chunks


def test_resolve_pipeline_chunks_prefers_direct():
    client = MagicMock()
    with patch(
        "libs.patient_document_runs.chunk_resolver.list_document_chunks_normalized",
        return_value=[{"id": "c1", "ordinal": 0, "text": "hello"}],
    ) as list_chunks:
        resolved = resolve_pipeline_chunks(
            client,
            document_reference_id="dr-1",
            referral_id="rr-1",
        )
    list_chunks.assert_called_once_with(client, document_reference_id="dr-1", limit=500)
    assert resolved.resolution == "direct"
    assert resolved.source_document_id == "dr-1"
    assert len(resolved.chunks) == 1


def test_resolve_pipeline_chunks_falls_back_to_bundle():
    client = MagicMock()

    def _list(client_arg, document_reference_id, limit=500):
        if document_reference_id == "000049831707:leo-referral-bundle":
            return [{"id": "c2", "ordinal": 1, "text": "bundle text"}]
        return []

    with patch(
        "libs.patient_document_runs.chunk_resolver.list_document_chunks_normalized",
        side_effect=_list,
    ):
        resolved = resolve_pipeline_chunks(
            client,
            document_reference_id="000049831707-clinical-information",
            referral_id="000049831707",
        )
    assert resolved.resolution == "referral_bundle"
    assert resolved.source_document_id == "000049831707:leo-referral-bundle"
    assert len(resolved.chunks) == 1


def test_resolve_pipeline_chunks_falls_back_to_sibling():
    client = MagicMock()
    client.run.return_value = [{"source_document_id": "DocumentReference-151063"}]

    def _list(client_arg, document_reference_id, limit=500):
        if document_reference_id == "DocumentReference-151063":
            return [{"id": "c3", "ordinal": 0, "text": "form"}]
        return []

    with patch(
        "libs.patient_document_runs.chunk_resolver.list_document_chunks_normalized",
        side_effect=_list,
    ):
        resolved = resolve_pipeline_chunks(
            client,
            document_reference_id="000049823877-clinical-information",
            referral_id="000049823877",
        )
    assert resolved.resolution == "referral_sibling"
    assert resolved.source_document_id == "DocumentReference-151063"
    assert len(resolved.chunks) == 1
