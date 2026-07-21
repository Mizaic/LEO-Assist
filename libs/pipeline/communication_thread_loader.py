"""Load A&G CommunicationRequest threads as LEO extraction units.

Atlas trace:
  DO: DO-728930A1
  DI: DI-16CE412B, DI-B5C78811
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from libs.cypher.communication_thread_queries import (
    LIST_CR_LEVEL_ATTACHMENTS,
    LIST_THREAD_WITH_MESSAGE_ATTACHMENTS,
    READ_FORMAL_AGR_RESPONSE,
)
from libs.pipeline.document_chunk_loader import (
    CHUNK_TEXT_SEPARATOR,
    GET_CHUNKS_BY_IDS,
    build_document_chunk_state,
)

COMMUNICATION_THREAD_MODE = "communication_thread"

_CATEGORY_PREFIX = {
    "REQUESTER": "[REQUESTER]",
    "RESPONDER": "[RESPONDER]",
    "FORMAL_RESPONSE": "[FORMAL_RESPONSE]",
    "ATTACHMENT": "[ATTACHMENT]",
}


def is_communication_thread_mode(state: dict[str, Any]) -> bool:
    return str(state.get("text_segmentation_mode") or "").strip() == (
        COMMUNICATION_THREAD_MODE
    )


def _prefix_segment(category: str, text: str) -> str:
    label = _CATEGORY_PREFIX.get(str(category or "").strip().upper(), "")
    body = str(text or "").strip()
    if not body:
        return ""
    return f"{label} {body}" if label else body


def _parse_sent_datetime(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.min
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min


def _attachment_chunk_rows(raw_chunks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_chunks, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw_chunks:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id") or "").strip()
        text = str(item.get("text") or "")
        if not chunk_id or not text.strip():
            continue
        rows.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "ordinal": int(item.get("ordinal") or 0),
                "char_start": 0,
                "char_end": len(text),
            }
        )
    rows.sort(key=lambda row: (int(row.get("ordinal") or 0), row["chunk_id"]))
    return rows


def _chunk_attachment_sentences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    loaded = build_document_chunk_state(rows)
    sentences: list[dict[str, Any]] = []
    for sentence in loaded.get("sentences") or []:
        text = _prefix_segment("ATTACHMENT", str(sentence.get("text") or ""))
        if not text:
            continue
        sentences.append(
            {
                "sentence_id": sentence["sentence_id"],
                "text": text,
                "start": sentence.get("start", 0),
                "end": sentence.get("end", len(text)),
                "persist_source_label": "Chunk",
            }
        )
    return sentences


def _note_sentence(
    communication_id: str, category: str, note: str
) -> dict[str, Any] | None:
    text = _prefix_segment(category, note)
    if not text:
        return None
    return {
        "sentence_id": communication_id,
        "text": text,
        "start": 0,
        "end": len(text),
        "persist_source_label": "Communication",
    }


def build_communication_thread_state(
    *,
    communication_request_id: str,
    thread_rows: list[dict[str, Any]],
    cr_attachment_rows: list[dict[str, Any]],
    agr_response_text: str | None,
    extra_chunk_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble ordered sentences for communication_thread extraction."""
    ordered = sorted(
        thread_rows,
        key=lambda row: _parse_sent_datetime(row.get("sent_datetime")),
    )
    sentences: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()

    for row in ordered:
        comm_id = str(row.get("communication_id") or "").strip()
        note = str(row.get("note") or "")
        category = str(row.get("category") or "REQUESTER")
        note_sentence = _note_sentence(comm_id, category, note)
        if note_sentence:
            sentences.append(note_sentence)
        for chunk_sentence in _chunk_attachment_sentences(
            _attachment_chunk_rows(row.get("attachment_chunks"))
        ):
            chunk_id = str(chunk_sentence.get("sentence_id") or "")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            sentences.append(chunk_sentence)

    cr_rows = [
        {
            "chunk_id": str(row.get("chunk_id") or "").strip(),
            "text": str(row.get("text") or ""),
            "ordinal": int(row.get("ordinal") or 0),
            "char_start": 0,
            "char_end": len(str(row.get("text") or "")),
        }
        for row in cr_attachment_rows
        if str(row.get("chunk_id") or "").strip() and str(row.get("text") or "").strip()
    ]
    for chunk_sentence in _chunk_attachment_sentences(cr_rows):
        chunk_id = str(chunk_sentence.get("sentence_id") or "")
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        sentences.append(chunk_sentence)

    if extra_chunk_rows:
        for chunk_sentence in _chunk_attachment_sentences(extra_chunk_rows):
            chunk_id = str(chunk_sentence.get("sentence_id") or "")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            sentences.append(chunk_sentence)

    response_text = str(agr_response_text or "").strip()
    if response_text:
        response_id = f"{communication_request_id}:response"
        response_sentence = _note_sentence(
            response_id, "FORMAL_RESPONSE", response_text
        )
        if response_sentence:
            sentences.append(response_sentence)

    if not sentences:
        return {
            "sentences": [],
            "encounter_text": "",
            "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
            "errors": [
                "communication_thread mode requires thread, attachment, or AGR text"
            ],
        }

    encounter_text = CHUNK_TEXT_SEPARATOR.join(
        str(s.get("text") or "") for s in sentences if s.get("text")
    )
    return {
        "sentences": sentences,
        "encounter_text": encounter_text,
        "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
    }


def load_communication_thread_from_neo4j(
    client: Any,
    communication_request_id: str,
    *,
    chunk_ids: list[str] | None = None,
) -> dict[str, Any]:
    cr_id = str(communication_request_id or "").strip()
    if not cr_id:
        return {
            "sentences": [],
            "encounter_text": "",
            "text_segmentation_mode": COMMUNICATION_THREAD_MODE,
            "errors": ["communication_request_id is required"],
        }

    thread_rows = client.run(
        LIST_THREAD_WITH_MESSAGE_ATTACHMENTS,
        communication_request_id=cr_id,
    )
    cr_attachment_rows = client.run(
        LIST_CR_LEVEL_ATTACHMENTS,
        communication_request_id=cr_id,
    )
    agr_rows = client.run(
        READ_FORMAL_AGR_RESPONSE,
        communication_request_id=cr_id,
    )
    agr_text = str((agr_rows or [{}])[0].get("response_text") or "").strip() or None

    extra_chunk_rows: list[dict[str, Any]] = []
    explicit_ids = [
        str(item).strip() for item in (chunk_ids or []) if str(item).strip()
    ]
    if explicit_ids:
        extra_chunk_rows = list(
            client.run(GET_CHUNKS_BY_IDS, chunk_ids=explicit_ids) or []
        )

    return build_communication_thread_state(
        communication_request_id=cr_id,
        thread_rows=[dict(row) for row in (thread_rows or [])],
        cr_attachment_rows=[dict(row) for row in (cr_attachment_rows or [])],
        agr_response_text=agr_text,
        extra_chunk_rows=extra_chunk_rows,
    )
