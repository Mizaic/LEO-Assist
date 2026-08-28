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
    """Return attachment sentences keyed on their real Neo4j chunk id.

    ``build_document_chunk_state`` is called once per message, so its
    ``s0``-style labels restart every time.  Labelling is therefore left
    to ``_append_chunk_sentences``, which owns a counter for the whole
    assembled thread.
    """
    # An attachment on a clinician's email is not the taught referral form,
    # so no schema lookup is attempted. See
    # tests/test_communication_attachment_no_schema_lookup.py.
    loaded = build_document_chunk_state(rows, resolve_schema=False)
    sentences: list[dict[str, Any]] = []
    for sentence in loaded.get("sentences") or []:
        text = _prefix_segment("ATTACHMENT", str(sentence.get("text") or ""))
        chunk_id = str(sentence.get("chunk_id") or "").strip()
        if not text or not chunk_id:
            continue
        sentences.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "start": sentence.get("start", 0),
                "end": sentence.get("end", len(text)),
                "persist_source_label": "Chunk",
            }
        )
    return sentences


def _append_chunk_sentences(
    rows: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
    chunk_id_by_sentence_id: dict[str, str],
) -> None:
    """Append attachment sentences under labels unique to this thread.

    Dedupe is on the real chunk id, never on the label.  The same
    attachment quoted on two messages collapses to one; two different
    attachments both survive, which a label-based check got wrong
    because both arrived as ``s0``.
    """
    seen = set(chunk_id_by_sentence_id.values())
    for sentence in _chunk_attachment_sentences(rows):
        chunk_id = str(sentence.pop("chunk_id"))
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        label = f"s{len(chunk_id_by_sentence_id)}"
        chunk_id_by_sentence_id[label] = chunk_id
        sentences.append({"sentence_id": label, "chunk_id": chunk_id, **sentence})


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
    chunk_id_by_sentence_id: dict[str, str] = {}

    for row in ordered:
        comm_id = str(row.get("communication_id") or "").strip()
        note = str(row.get("note") or "")
        category = str(row.get("category") or "REQUESTER")
        note_sentence = _note_sentence(comm_id, category, note)
        if note_sentence:
            sentences.append(note_sentence)
        _append_chunk_sentences(
            _attachment_chunk_rows(row.get("attachment_chunks")),
            sentences,
            chunk_id_by_sentence_id,
        )

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
    _append_chunk_sentences(cr_rows, sentences, chunk_id_by_sentence_id)

    if extra_chunk_rows:
        _append_chunk_sentences(extra_chunk_rows, sentences, chunk_id_by_sentence_id)

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
            "chunk_id_by_sentence_id": {},
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
        "chunk_id_by_sentence_id": chunk_id_by_sentence_id,
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
            "chunk_id_by_sentence_id": {},
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
