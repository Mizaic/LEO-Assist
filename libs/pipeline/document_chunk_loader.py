"""Load HCCP-prepared :Chunk nodes as LEO extraction units (document_chunks mode).

Atlas trace:
  DO: DO-728930A1
  DI: DI-16CE412B, DI-B5C78811
  Also: DI-5C9CA57B / DO-7010394B (form checkbox normalisation at extract input)
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")
"""

from __future__ import annotations

import re
from typing import Any

from libs.ner.form_checkbox_normalizer import normalize_form_checkbox_text

# The HCCP bundle assembler (combine_referral_markdown in HCCP-Agents) writes a
# header line before each document:  --- Document: {title} ---
# PDF attachments (e.g. the e-RS "Clinical Information.pdf" wrapper) are
# administrative boilerplate.  Including them in encounter_text contaminates
# the form fingerprint, inflates the wrapper penalty, and degrades few-shot
# similarity -- causing false-positive pauses even after teaching.
# This pattern strips the first PDF-titled section and everything after it.
_PDF_BOUNDARY_RE = re.compile(
    r"\n*---\s*Document:[^\n]+\.pdf\s*---.*$",
    re.DOTALL | re.IGNORECASE,
)

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


def strip_pdf_attachments(text: str) -> str:
    """Remove PDF attachment sections from a referral bundle encounter text.

    The HCCP bundle assembler prefixes every document with a header line:
        --- Document: {title} ---
    This function removes the first PDF-titled section and everything after
    it, keeping only the primary referral form content (the .doc file).

    The individual :Chunk sentences are left untouched so SNOMED concept
    provenance can still be linked back to the correct chunk node.
    """
    return _PDF_BOUNDARY_RE.sub("", text).strip()


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
    return (
        str(state.get("text_segmentation_mode") or "").strip() == DOCUMENT_CHUNKS_MODE
    )


def chunk_ids_from_state(state: dict[str, Any]) -> list[str]:
    raw = state.get("chunk_ids") or []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _normalise_chunk_texts(raw_texts: list[str]) -> list[str]:
    """Normalise chunk texts, using chunk_section_map when a schema is known."""
    if not raw_texts:
        return []
    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline.document_quality import form_fingerprint
    from libs.pipeline.form_schema_normalizer import normalise_with_schema
    from libs.pipeline.form_schema_store import load_form_schema

    fingerprint = form_fingerprint(CHUNK_TEXT_SEPARATOR.join(raw_texts))
    client = PatientGraphClient()
    try:
        schema = load_form_schema(client, fingerprint)
    finally:
        client.close()
    if schema is not None and schema.chunk_section_map:
        joined = normalise_with_schema(schema, raw_texts, schema.chunk_section_map)
        parts = joined.split(CHUNK_TEXT_SEPARATOR)
        if len(parts) == len(raw_texts):
            return parts
    return [normalize_form_checkbox_text(text) for text in raw_texts]


def build_document_chunk_state(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Map Neo4j chunk rows to pipeline state (sentences + encounter_text)."""
    sentences: list[dict[str, Any]] = []
    text_parts: list[str] = []
    offset = 0

    prepared: list[dict[str, Any]] = []
    for row in rows:
        chunk_id = str(row.get("chunk_id") or "").strip()
        text_raw = str(row.get("text") or "")
        if not chunk_id or not text_raw.strip():
            continue
        prepared.append({"chunk_id": chunk_id, "text_raw": text_raw, "row": row})

    normalised_texts = _normalise_chunk_texts([p["text_raw"] for p in prepared])

    for idx, item in enumerate(prepared):
        chunk_id = item["chunk_id"]
        text_raw = item["text_raw"]
        row = item["row"]
        text = normalised_texts[idx]

        char_start = row.get("char_start")
        char_end = row.get("char_end")
        if char_start is None or char_end is None or int(char_end) <= int(char_start):
            char_start = offset
            char_end = offset + len(text_raw)
            offset = char_end + len(CHUNK_TEXT_SEPARATOR)
        else:
            char_start = int(char_start)
            char_end = int(char_end)

        sentences.append(
            {
                "sentence_id": chunk_id,
                "text": text,
                "text_raw": text_raw,
                "start": char_start,
                "end": char_end,
            }
        )
        text_parts.append(text_raw)

    encounter_text = strip_pdf_attachments(CHUNK_TEXT_SEPARATOR.join(text_parts))
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
