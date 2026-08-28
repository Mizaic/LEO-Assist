"""Extraction subgraph must not carry stale loader errors after chunk reload."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline_graph.subgraphs.extraction import load_document_chunks


def test_load_document_chunks_drops_stale_loader_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.pipeline.document_chunk_loader.load_document_chunks_from_neo4j",
        lambda _client, _chunk_ids, **_scope: {
            "sentences": [
                {"sentence_id": "c1", "text": "Dysphagia", "start": 0, "end": 9}
            ],
            "encounter_text": "Dysphagia",
            "text_segmentation_mode": "document_chunks",
        },
    )
    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=MagicMock(),
    ):
        result = load_document_chunks(
            {
                "chunk_ids": ["c1"],
                "text_segmentation_mode": "document_chunks",
                "errors": ["Tenant id is required to validate trigger chunks."],
            }
        )
    assert result.get("sentences")
    assert result.get("errors") == []
