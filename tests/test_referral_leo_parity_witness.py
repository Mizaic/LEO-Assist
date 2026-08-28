"""Integration witness: LEO document-chunk mode publish contract."""

from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    build_document_chunk_state,
    merge_referral_message_fields,
)


def test_referral_received_message_carries_document_chunk_fields() -> None:
    body = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "chunk_ids": ["c1", "c2"],
        "document_reference_id": "ubrn-1:leo-referral-bundle",
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        "context": {"ubrn": "ubrn-1", "referral_id": "ubrn-1"},
    }
    context = merge_referral_message_fields(body)
    assert context["chunk_ids"] == ["c1", "c2"]
    assert context["text_segmentation_mode"] == DOCUMENT_CHUNKS_MODE


def test_document_chunk_state_matches_hccp_prep_shape() -> None:
    table = "| Hb | 120 g/L |"
    loaded = build_document_chunk_state(
        [
            {
                "chunk_id": "chunk-1",
                "text": table,
                "ordinal": 1,
                "char_start": 0,
                "char_end": len(table),
            }
        ]
    )
    # The extractor is addressed by the short label; the graph write is
    # addressed by the real chunk id behind it.
    assert loaded["sentences"][0]["sentence_id"] == "s0"
    assert loaded["sentences"][0]["chunk_id"] == "chunk-1"
    assert loaded["chunk_id_by_sentence_id"] == {"s0": "chunk-1"}
    assert loaded["sentences"][0]["text"] == table
