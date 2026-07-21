"""Tests for A&G communication_thread extraction mode."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.pipeline.communication_thread_loader import (
    COMMUNICATION_THREAD_MODE,
    build_communication_thread_state,
    is_communication_thread_mode,
    load_communication_thread_from_neo4j,
)
from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    merge_referral_message_fields,
)


def test_is_communication_thread_mode() -> None:
    assert is_communication_thread_mode(
        {"text_segmentation_mode": COMMUNICATION_THREAD_MODE}
    )
    assert not is_communication_thread_mode(
        {"text_segmentation_mode": DOCUMENT_CHUNKS_MODE}
    )
    assert not is_communication_thread_mode({})


def test_build_thread_state_orders_by_sent_datetime() -> None:
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c-responder",
                "note": "Reply note",
                "category": "RESPONDER",
                "sent_datetime": "2026-01-02T10:00:00",
                "attachment_chunks": [],
            },
            {
                "communication_id": "c-requester",
                "note": "Question note",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": [],
            },
        ],
        cr_attachment_rows=[],
        agr_response_text=None,
    )
    assert [s["sentence_id"] for s in loaded["sentences"]] == [
        "c-requester",
        "c-responder",
    ]
    assert loaded["sentences"][0]["text"].startswith("[REQUESTER]")
    assert loaded["sentences"][1]["text"].startswith("[RESPONDER]")


def test_build_thread_state_thread_only_without_has_document() -> None:
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c1",
                "note": "GP question",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": [],
            }
        ],
        cr_attachment_rows=[],
        agr_response_text="Formal advice text",
    )
    assert len(loaded["sentences"]) == 2
    assert all(
        s.get("persist_source_label") == "Communication" for s in loaded["sentences"]
    )
    assert loaded["sentences"][-1]["text"].startswith("[FORMAL_RESPONSE]")
    assert "errors" not in loaded


def test_build_thread_state_skips_has_document_without_chunks() -> None:
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c1",
                "note": "Question",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": [
                    {"chunk_id": "", "text": "", "ordinal": 1},
                ],
            }
        ],
        cr_attachment_rows=[],
        agr_response_text=None,
    )
    assert len(loaded["sentences"]) == 1
    assert "[ATTACHMENT]" not in loaded["encounter_text"]


def test_build_thread_state_interleaves_message_attachments_when_present() -> None:
    table_text = "| Test | Result |\n| Hb | 120 g/L |"
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c1",
                "note": "See attachment",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": [
                    {"chunk_id": "chunk-a", "text": table_text, "ordinal": 1},
                ],
            }
        ],
        cr_attachment_rows=[],
        agr_response_text=None,
    )
    assert len(loaded["sentences"]) == 2
    assert loaded["sentences"][0]["persist_source_label"] == "Communication"
    assert loaded["sentences"][1]["persist_source_label"] == "Chunk"
    assert loaded["sentences"][1]["text"].startswith("[ATTACHMENT]")
    assert "| Hb |" in loaded["sentences"][1]["text"]


def test_build_thread_state_appends_cr_level_attachments_before_agr_when_present() -> (
    None
):
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c1",
                "note": "Question",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": [],
            }
        ],
        cr_attachment_rows=[
            {
                "chunk_id": "cr-chunk",
                "text": "Request-level scan text",
                "ordinal": 1,
            }
        ],
        agr_response_text="Formal response",
    )
    ids = [s["sentence_id"] for s in loaded["sentences"]]
    assert ids == ["c1", "cr-chunk", "cr-1:response"]
    assert loaded["sentences"][1]["persist_source_label"] == "Chunk"


def test_build_thread_state_appends_formal_response_last() -> None:
    loaded = build_communication_thread_state(
        communication_request_id="cr-99",
        thread_rows=[],
        cr_attachment_rows=[],
        agr_response_text="Provider advice",
    )
    assert len(loaded["sentences"]) == 1
    assert loaded["sentences"][0]["sentence_id"] == "cr-99:response"
    assert loaded["sentences"][0]["text"] == "[FORMAL_RESPONSE] Provider advice"


def test_build_thread_state_reuses_document_chunk_state_for_attachments() -> None:
    table_text = "| WBC | 5.2 |\n| RBC | 4.1 |"
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[],
        cr_attachment_rows=[
            {"chunk_id": "chunk-table", "text": table_text, "ordinal": 1},
        ],
        agr_response_text=None,
    )
    assert len(loaded["sentences"]) == 1
    assert table_text in loaded["sentences"][0]["text"]
    assert "\n|" in loaded["encounter_text"]


def test_load_from_neo4j_requires_communication_request_id() -> None:
    client = MagicMock()
    empty = load_communication_thread_from_neo4j(client, "")
    assert empty["errors"]
    client.run.assert_not_called()

    client = MagicMock()
    client.run.side_effect = [[], [], []]
    loaded = load_communication_thread_from_neo4j(client, "cr-empty")
    assert loaded["errors"]
    assert client.run.call_count == 3


def test_merge_handoff_copies_ubrn_and_mode() -> None:
    body = {
        "communication_request_id": "cr-1",
        "ubrn": "UBRN123",
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
        "context": {"patient_id": "p1"},
    }
    context = merge_referral_message_fields(body)
    assert context["communication_request_id"] == "cr-1"
    assert context["ubrn"] == "UBRN123"
    assert context["text_segmentation_mode"] == COMMUNICATION_THREAD_MODE
    assert context["patient_id"] == "p1"
