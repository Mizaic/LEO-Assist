"""End-to-end parity: A&G scaffold -> loader -> mixed persist hints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline.communication_thread_loader import build_communication_thread_state
from libs.validation_lab.models import AgConversationTurn, ValidationCaseSpec


def test_ag_scaffold_loader_mixed_persist_source_labels() -> None:
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c1",
                "note": "See attachment",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": [
                    {"chunk_id": "chunk-a", "text": "Hb 120 g/L", "ordinal": 1},
                ],
            },
            {
                "communication_id": "c2",
                "note": "Thanks",
                "category": "RESPONDER",
                "sent_datetime": "2026-01-02T10:00:00",
                "attachment_chunks": [],
            },
        ],
        cr_attachment_rows=[],
        agr_response_text="Proceed with referral",
    )
    labels = [s.get("persist_source_label") for s in loaded["sentences"]]
    assert labels == ["Communication", "Chunk", "Communication", "Communication"]
    comm_ids = [
        s["sentence_id"]
        for s in loaded["sentences"]
        if s.get("persist_source_label") == "Communication"
    ]
    chunk_labels = [
        s["sentence_id"]
        for s in loaded["sentences"]
        if s.get("persist_source_label") == "Chunk"
    ]
    assert "c1" in comm_ids
    # Attachment chunks carry the short label the extractor echoes. The
    # real Neo4j chunk id the write must match sits in the reverse map.
    assert chunk_labels == ["s0"]
    assert loaded["chunk_id_by_sentence_id"] == {"s0": "chunk-a"}


def test_materialise_ag_case_builds_pipeline_message() -> None:
    from libs.validation_lab.pipeline import build_pipeline_message

    case = {
        "id": "case-1",
        "case_type": "ag",
        "patient_id": "p1",
        "communication_request_id": "cr-1",
        "ubrn": "UBRN1",
        "chunk_ids": [],
    }
    body = build_pipeline_message(
        case,
        run_id="run-1",
        plan_id="pd-referral-assessment",
        dry_run=False,
    )
    assert body["text_segmentation_mode"] == "communication_thread"
    assert body["mode"] == "ag_assessment"


def test_ag_scaffold_writes_thread_graph() -> None:
    from libs.validation_lab.ag_scaffold import scaffold_ag_case

    client = MagicMock()
    session = MagicMock()
    client.session.return_value.__enter__.return_value = session
    spec = ValidationCaseSpec(
        case_id="ag-case-1",
        title="A&G test",
        case_type="ag",
        ag_thread=[
            AgConversationTurn(category="REQUESTER", note="Question"),
            AgConversationTurn(category="RESPONDER", note="Answer"),
        ],
        ag_response_text="Formal advice",
    )
    with patch(
        "libs.validation_lab.ag_scaffold.split_into_chunks",
        return_value=[],
    ):
        graph = scaffold_ag_case(client, spec)
    assert graph["communication_request_id"]
    assert graph["ubrn"]
    assert session.run.call_count >= 4
