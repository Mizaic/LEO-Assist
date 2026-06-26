"""Tests for HCCP referral document-chunk extraction mode."""

from __future__ import annotations

from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    build_document_chunk_state,
    is_document_chunks_mode,
    merge_referral_message_fields,
)


def test_merge_referral_message_fields_copies_top_level_into_context() -> None:
    body = {
        "chunk_ids": ["c1", "c2"],
        "document_reference_id": "dr-1",
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "referral_id": "ref-1",
        "context": {"patient_id": "p1"},
    }
    context = merge_referral_message_fields(body)
    assert context["chunk_ids"] == ["c1", "c2"]
    assert context["document_reference_id"] == "dr-1"
    assert context["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE
    assert context["referral_id"] == "ref-1"
    assert context["patient_id"] == "p1"


def test_build_document_chunk_state_preserves_table_text() -> None:
    table_text = "| Test | Result |\n| Hb | 120 g/L |"
    rows = [
        {
            "chunk_id": "chunk-a",
            "text": table_text,
            "ordinal": 1,
            "char_start": 0,
            "char_end": len(table_text),
        }
    ]
    loaded = build_document_chunk_state(rows)
    assert len(loaded["sentences"]) == 1
    assert loaded["sentences"][0]["text"] == table_text
    assert "| Hb |" in loaded["encounter_text"]
    assert loaded["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE


def test_is_document_chunks_mode() -> None:
    assert is_document_chunks_mode({"text_segmentation_mode": DOCUMENT_CHUNKS_MODE})
    assert not is_document_chunks_mode({"text_segmentation_mode": "encounter_sentences"})
    assert not is_document_chunks_mode({})


def test_load_document_chunks_skips_sentence_splitter(monkeypatch) -> None:
    from libs.pipeline_graph.subgraphs.extraction import (
        load_document_chunks,
        split_sentences,
    )

    table_text = "| WBC | 5.2 |\n| RBC | 4.1 |"
    state = {
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "sentences": [
            {
                "sentence_id": "chunk-1",
                "text": table_text,
                "start": 0,
                "end": len(table_text),
            }
        ],
    }
    loaded = load_document_chunks(state)
    assert loaded["sentences"][0]["text"] == table_text
    assert "\n|" in loaded["encounter_text"]

    split_called: list[bool] = []

    def _track_split(_state):
        split_called.append(True)
        return split_sentences(_state)

    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.extraction.split_sentences",
        _track_split,
    )
    load_document_chunks(state)
    assert not split_called
