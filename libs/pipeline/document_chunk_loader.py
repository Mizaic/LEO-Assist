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
from libs.pipeline_contracts.text import (
    Deletion,
    RawChunk,
    SourceText,
    build_source_text,
)

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


def pdf_attachment_deletions(text: str) -> tuple[Deletion, ...]:
    """Return the ranges ``strip_pdf_attachments`` removes from ``text``.

    Same removals, expressed as coordinates instead of a new string, so
    ``SourceText`` can remap offsets around them.  Rebuilding ``text``
    minus these ranges reproduces ``strip_pdf_attachments`` byte for
    byte -- that equivalence is pinned by test.
    """
    match = _PDF_BOUNDARY_RE.search(text)
    kept_end = match.start() if match else len(text)
    kept = text[:kept_end]

    deletions: list[Deletion] = []
    leading = len(kept) - len(kept.lstrip())
    if leading:
        deletions.append(
            Deletion(kind="leading_whitespace", raw_start=0, raw_end=leading)
        )
    trailing = len(kept) - len(kept.rstrip())
    if trailing:
        deletions.append(
            Deletion(
                kind="trailing_whitespace",
                raw_start=kept_end - trailing,
                raw_end=kept_end,
            )
        )
    if match:
        deletions.append(
            Deletion(
                kind="pdf_attachment",
                raw_start=match.start(),
                raw_end=match.end(),
            )
        )
    return tuple(deletions)


def build_chunk_source_text(chunk_id_texts: list[tuple[str, str]]) -> SourceText:
    """Build the single coordinate space for a referral bundle's chunks."""
    return build_source_text(
        [RawChunk(chunk_id=cid, text=text) for cid, text in chunk_id_texts],
        separator=CHUNK_TEXT_SEPARATOR,
        normalise=pdf_attachment_deletions,
    )


def bundle_fingerprint(chunk_texts: list[str]) -> str:
    """Return the form fingerprint for a referral bundle's chunk texts.

    The fingerprint covers only the primary referral document. PDF
    attachments vary between referrals of the same form, so including
    them would give the same form a different fingerprint each time and
    the taught :FormSchema would never be found. The teach dialog
    fingerprints the same stripped text, so both sides agree.
    """
    from libs.pipeline.document_quality import form_fingerprint

    joined = CHUNK_TEXT_SEPARATOR.join(chunk_texts)
    return form_fingerprint(strip_pdf_attachments(joined))


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


def _resolve_chunk_schema(
    raw_texts: list[str],
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> tuple[Any, dict[str, str]]:
    """Return the taught schema and inspector state fields for these chunks."""
    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline.form_schema_store import (
        form_schema_state_fields,
        resolve_form_schema_traced,
    )

    if not raw_texts:
        return None, form_schema_state_fields("none")
    fingerprint = bundle_fingerprint(raw_texts)
    client = PatientGraphClient()
    try:
        schema, match, loaded_key, label = resolve_form_schema_traced(
            client,
            fingerprint,
            organization_id=organization_id,
            service_id=service_id,
            ers_service_id=ers_service_id,
        )
    finally:
        client.close()
    return schema, form_schema_state_fields(match, loaded_key, label)


def _normalise_chunk_texts(
    raw_texts: list[str],
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> tuple[list[str], dict[str, str]]:
    """Normalise chunk texts, using chunk_section_map when a schema is known."""
    from libs.pipeline.form_schema_normalizer import normalise_chunks_with_schema

    schema, fields = _resolve_chunk_schema(
        raw_texts,
        organization_id=organization_id,
        service_id=service_id,
        ers_service_id=ers_service_id,
    )
    if not raw_texts:
        return [], fields
    if schema is not None and schema.sections:
        return (
            normalise_chunks_with_schema(schema, raw_texts, schema.chunk_section_map),
            fields,
        )
    return [normalize_form_checkbox_text(text) for text in raw_texts], fields


def _prepare_chunk_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop rows with no id or no printable text, keeping document order."""
    prepared: list[dict[str, Any]] = []
    for row in rows:
        chunk_id = str(row.get("chunk_id") or "").strip()
        text_raw = str(row.get("text") or "")
        if not chunk_id or not text_raw.strip():
            continue
        prepared.append({"chunk_id": chunk_id, "text_raw": text_raw, "row": row})
    return prepared


def _legacy_chunk_bounds(
    row: dict[str, Any], text_raw: str, offset: int
) -> tuple[int, int, int]:
    """Return the legacy ``(start, end, next_offset)`` for one chunk.

    Kept exactly as-is: these offsets carry two different meanings
    depending on whether the row supplied them, and downstream guards
    still read them.  Slice 5 retires this in favour of SourceText.
    """
    char_start = row.get("char_start")
    char_end = row.get("char_end")
    if char_start is None or char_end is None or int(char_end) <= int(char_start):
        start = offset
        end = offset + len(text_raw)
        return start, end, end + len(CHUNK_TEXT_SEPARATOR)
    return int(char_start), int(char_end), offset


def _build_legacy_sentences(
    prepared: list[dict[str, Any]], normalised_texts: list[str]
) -> list[dict[str, Any]]:
    """Build the legacy sentence dicts, offsets and all."""
    sentences: list[dict[str, Any]] = []
    offset = 0
    for index, item in enumerate(prepared):
        text_raw = item["text_raw"]
        start, end, offset = _legacy_chunk_bounds(item["row"], text_raw, offset)
        sentences.append(
            {
                "sentence_id": item["chunk_id"],
                "text": normalised_texts[index],
                "text_raw": text_raw,
                "start": start,
                "end": end,
            }
        )
    return sentences


def build_document_chunk_state(
    rows: list[dict[str, Any]],
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> dict[str, Any]:
    """Map Neo4j chunk rows to pipeline state (sentences + encounter_text)."""
    prepared = _prepare_chunk_rows(rows)
    normalised_texts, schema_fields = _normalise_chunk_texts(
        [p["text_raw"] for p in prepared],
        organization_id=organization_id,
        service_id=service_id,
        ers_service_id=ers_service_id,
    )
    sentences = _build_legacy_sentences(prepared, normalised_texts)
    text_parts = [p["text_raw"] for p in prepared]

    encounter_text = strip_pdf_attachments(CHUNK_TEXT_SEPARATOR.join(text_parts))
    return {
        "sentences": sentences,
        "encounter_text": encounter_text,
        "source_text": build_chunk_source_text(
            [(p["chunk_id"], p["text_raw"]) for p in prepared]
        ),
        "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
        **schema_fields,
    }


def load_document_chunks_from_neo4j(
    client: Any,
    chunk_ids: list[str],
    organization_id: str = "",
    service_id: str = "",
    ers_service_id: str = "",
) -> dict[str, Any]:
    if not chunk_ids:
        from libs.pipeline.form_schema_store import form_schema_state_fields

        return {
            "sentences": [],
            "encounter_text": "",
            "source_text": build_chunk_source_text([]),
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "errors": ["document_chunks mode requires non-empty chunk_ids"],
            **form_schema_state_fields("none"),
        }
    rows = client.run(GET_CHUNKS_BY_IDS, chunk_ids=chunk_ids)
    loaded = build_document_chunk_state(
        rows or [],
        organization_id=organization_id,
        service_id=service_id,
        ers_service_id=ers_service_id,
    )
    if not loaded.get("sentences"):
        loaded["errors"] = ["no Chunk nodes found for supplied chunk_ids"]
    return loaded
