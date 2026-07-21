"""Load HCCP-prepared :Chunk nodes as LEO extraction units (document_chunks mode)."""

from __future__ import annotations

from typing import Any

DOCUMENT_CHUNKS_MODE = "document_chunks"
ENCOUNTER_SENTENCES_MODE = "encounter_sentences"
CHUNK_TEXT_SEPARATOR = "\n\n"

GET_CHUNKS_BY_IDS = """
UNWIND $chunk_ids AS cid
MATCH (c:Chunk {id: cid})
RETURN c.id AS chunk_id,
       c.text AS text,
       c.ordinal AS ordinal,
       coalesce(c.char_start, 0) AS char_start,
       coalesce(c.char_end, 0) AS char_end
ORDER BY ordinal ASC
"""


def merge_referral_message_fields(body: dict[str, Any]) -> dict[str, Any]:
    """Copy top-level referral chunk fields into context for durable steps."""
    context = dict(body.get("context") or {})
    for key in (
        "chunk_ids",
        "communication_request_id",
        "document_reference_id",
        "text_segmentation_mode",
        "referral_id",
        "ubrn",
        "guideline_ids",
    ):
        if key in body and body[key] is not None and key not in context:
            context[key] = body[key]
    return context


def is_document_chunks_mode(state: dict[str, Any]) -> bool:
    return str(state.get("text_segmentation_mode") or "").strip() == DOCUMENT_CHUNKS_MODE


def chunk_ids_from_state(state: dict[str, Any]) -> list[str]:
    raw = state.get("chunk_ids") or []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def build_document_chunk_state(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Map Neo4j chunk rows to pipeline state (sentences + encounter_text)."""
    sentences: list[dict[str, Any]] = []
    text_parts: list[str] = []
    offset = 0

    for row in rows:
        chunk_id = str(row.get("chunk_id") or "").strip()
        text = str(row.get("text") or "")
        if not chunk_id or not text.strip():
            continue

        char_start = row.get("char_start")
        char_end = row.get("char_end")
        if char_start is None or char_end is None or int(char_end) <= int(char_start):
            char_start = offset
            char_end = offset + len(text)
            offset = char_end + len(CHUNK_TEXT_SEPARATOR)
        else:
            char_start = int(char_start)
            char_end = int(char_end)

        sentences.append(
            {
                "sentence_id": chunk_id,
                "text": text,
                "start": char_start,
                "end": char_end,
            }
        )
        text_parts.append(text)

    encounter_text = CHUNK_TEXT_SEPARATOR.join(text_parts)
    return {
        "sentences": sentences,
        "encounter_text": encounter_text,
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
    }


def load_document_chunks_from_neo4j(
    client: Any,
    chunk_ids: list[str],
) -> dict[str, Any]:
    if not chunk_ids:
        return {
            "sentences": [],
            "encounter_text": "",
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "errors": ["document_chunks mode requires non-empty chunk_ids"],
        }
    rows = client.run(GET_CHUNKS_BY_IDS, chunk_ids=chunk_ids)
    loaded = build_document_chunk_state(rows or [])
    if not loaded.get("sentences"):
        loaded["errors"] = ["no Chunk nodes found for supplied chunk_ids"]
    return loaded
