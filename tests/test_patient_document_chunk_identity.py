"""Tests for legacy chunk id normalization."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.cypher.chunk_queries import chunk_sha256, make_chunk_id
from libs.patient_document_runs.chunk_identity import (
    chunk_ordinal,
    list_document_chunks_normalized,
    normalize_chunk_row,
    resolve_chunk_id,
)


def test_resolve_chunk_id_synthesizes_legacy_id():
    doc_id = "DocumentReference-151066"
    text = "HDT Internal Use Only"
    row = {
        "id": "",
        "r_ordinal": None,
        "c_ordinal": 0,
        "chunk_idx": 0,
        "text": text,
    }
    expected = make_chunk_id(doc_id, 0, chunk_sha256(text))
    assert resolve_chunk_id(doc_id, row) == expected


def test_chunk_ordinal_prefers_chunk_idx_over_zero_ordinal():
    row = {"r_ordinal": None, "c_ordinal": 0, "chunk_idx": 7, "text": "hello"}
    assert chunk_ordinal(row) == 7


def test_resolve_chunk_id_repairs_mismatched_legacy_id():
    doc_id = "DocumentReference-151066"
    text = "HDT Internal Use Only"
    row = {
        "id": "3834d7d89b6184b84a1b0de69791083d",
        "r_ordinal": None,
        "c_ordinal": 0,
        "chunk_idx": 3,
        "text": text,
    }
    expected = make_chunk_id(doc_id, 3, chunk_sha256(text))
    assert resolve_chunk_id(doc_id, row) == expected


def test_list_document_chunks_normalized_backfills_missing_ids():
    client = MagicMock()
    client.run.side_effect = [
        [{"id": "", "r_ordinal": None, "c_ordinal": 0, "chunk_idx": 0, "text": "chunk one"}],
        None,
    ]
    chunks = list_document_chunks_normalized(
        client,
        document_reference_id="DocumentReference-151066",
        limit=10,
    )
    assert len(chunks) == 1
    assert chunks[0]["id"]
    assert chunks[0]["text"] == "chunk one"
    assert client.run.call_count == 2
    backfill_call = client.run.call_args_list[1].kwargs
    assert backfill_call["text"] == "chunk one"
    assert backfill_call["ordinal"] == 0


def test_normalize_chunk_row_preserves_existing_id():
    text = "hello"
    doc_id = "dr-1"
    chunk_id = make_chunk_id(doc_id, 2, chunk_sha256(text))
    row = {"id": chunk_id, "c_ordinal": 2, "text": text}
    out = normalize_chunk_row(doc_id, row)
    assert out["id"] == chunk_id
    assert out["legacy_missing_id"] is False
