"""Load HCCP-prepared :Chunk nodes as LEO extraction units (document_chunks mode).

Atlas trace:
  DO: DO-728930A1
  DI: DI-16CE412B, DI-B5C78811
  Also: DI-5C9CA57B / DO-7010394B (form checkbox normalisation at extract input)
  Also: DI-E21DF9EF / DO-E458EEC5 (per-document form recognition)
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")
"""

from __future__ import annotations

import re
from functools import partial
from typing import Any

from libs.form_recognition.recogniser import Outcome
from libs.neo4j_client import client as neo4j_client
from libs.pipeline.document_role import seal_administrative_documents
from libs.pipeline.form_recognition_apply import (
    recognise_texts,
    recognition_fields,
    rewrite_chunks,
)
from libs.pipeline.form_schema_candidates import load_candidate_schemas
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_store import form_schema_state_fields
from libs.pipeline_contracts.text import (
    Deletion,
    RawChunk,
    SourceText,
    build_source_text,
)

# Printed guidance blocks must not become findings. Document role already
# seals administrative cover sheets. Do not reseal a clinical PDF here --
# the e-RS Clinical Information form carries reason-for-referral and results.
_NON_EXTRACTABLE_CHUNK_RE = re.compile(
    r"^\s*Points\s+to\s+remember",
    re.IGNORECASE,
)

NON_EXTRACTABLE_MARKER = "[NON_EXTRACTABLE]"

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


def _mark_non_extractable_chunk(text: str) -> str:
    """Mark every line in a guidance block as non-extractable.

    A "Points to remember" block is printed guidance, not patient narrative.
    Every line is prefixed with the marker so that llm_facing_text removes
    the full block, not just the heading line. The raw text is kept in
    encounter_text so span resolution works.
    """
    if not text or not _NON_EXTRACTABLE_CHUNK_RE.search(text):
        return text
    marked_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(NON_EXTRACTABLE_MARKER):
            marked_lines.append(f"{NON_EXTRACTABLE_MARKER} {stripped}")
        else:
            marked_lines.append(line)
    return "\n".join(marked_lines)


def bundle_trim_deletions(text: str) -> tuple[Deletion, ...]:
    """Return the ranges trimmed from ``text`` to build ``encounter_text``.

    Extraction reads the whole bundle, attachments included, so the only
    difference between the raw join and what extraction sees is the outer
    whitespace. Expressed as coordinates rather than a new string so
    ``SourceText`` can remap offsets. Rebuilding ``text`` minus these
    ranges reproduces ``text.strip()`` byte for byte -- pinned by test.
    """
    if not text:
        return ()
    if not text.strip():
        return (Deletion(kind="leading_whitespace", raw_start=0, raw_end=len(text)),)

    deletions: list[Deletion] = []
    leading = len(text) - len(text.lstrip())
    if leading:
        deletions.append(
            Deletion(kind="leading_whitespace", raw_start=0, raw_end=leading)
        )
    trailing = len(text) - len(text.rstrip())
    if trailing:
        deletions.append(
            Deletion(
                kind="trailing_whitespace",
                raw_start=len(text) - trailing,
                raw_end=len(text),
            )
        )
    return tuple(deletions)


def build_chunk_source_text(chunk_id_texts: list[tuple[str, str]]) -> SourceText:
    """Build the single coordinate space for a referral bundle's chunks."""
    return build_source_text(
        [RawChunk(chunk_id=cid, text=text) for cid, text in chunk_id_texts],
        separator=CHUNK_TEXT_SEPARATOR,
        normalise=bundle_trim_deletions,
    )


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


def _candidate_schemas(organization_id: str) -> list[FormSchema]:
    """Active taught forms for this organisation, plus national forms."""
    client = neo4j_client.PatientGraphClient()
    try:
        return load_candidate_schemas(client, organization_id)
    finally:
        client.close()


def _recognise_chunks(raw_texts: list[str], organization_id: str) -> list[Outcome]:
    """Recognise each document. A failed lookup is RecognitionFailed."""
    return recognise_texts(raw_texts, partial(_candidate_schemas, organization_id))


_RECOGNITION_KEYS = (
    "form_schema_fingerprint",
    "form_schema_match",
    "form_schema_label",
    "form_recognition",
)
_SETTLED_MATCHES = frozenset(
    {"recognised", "unrecognised", "not_a_form", "failed", "not_applicable"}
)


def recognition_fields_from_state(
    state: dict[str, Any], encounter_text: str, organization_id: str = ""
) -> dict[str, Any]:
    """Reuse the bundle's recognition, or recognise the letter text now.

    A retired match value (``exact_hash``, ``org_service``) is not reused:
    the letter is recognised again, so it can never skip the check.
    """
    match = str(state.get("form_schema_match") or "").strip()
    if match in _SETTLED_MATCHES:
        fields: dict[str, Any] = dict(
            form_schema_state_fields(
                match,
                str(state.get("form_schema_fingerprint") or "none"),
                str(state.get("form_schema_label") or ""),
            )
        )
        fields["form_recognition"] = list(state.get("form_recognition") or [])
        return fields
    if not (encounter_text or "").strip():
        return {**form_schema_state_fields("none"), "form_recognition": []}
    outcomes = _recognise_chunks([encounter_text], organization_id)
    fields = recognition_fields([encounter_text], outcomes)
    return {key: fields[key] for key in _RECOGNITION_KEYS}


def _normalise_chunk_texts(
    raw_texts: list[str],
    organization_id: str = "",
    resolve_schema: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Normalise each document with its recognised form, or generic rules.

    ``resolve_schema=False`` skips recognition for callers whose chunks
    are not a referral form bundle, such as an attachment on a
    clinician's email. There is nothing to recognise, and the lookup
    would otherwise make the caller depend on the graph being reachable.
    """
    if not resolve_schema:
        return list(raw_texts), form_schema_state_fields("not_applicable")
    if not raw_texts:
        return [], form_schema_state_fields("none")
    outcomes = _recognise_chunks(raw_texts, organization_id)
    fields = recognition_fields(raw_texts, outcomes)
    rewritten = [
        _mark_non_extractable_chunk(seal_administrative_documents(text))
        for text in rewrite_chunks(raw_texts, outcomes)
    ]
    return rewritten, fields


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


def chunk_sentence_label(index: int) -> str:
    """Return the model-facing label for the chunk at ``index``.

    Every few-shot example in ``libs/prompts/extraction_examples.py``
    answers with an ``s0``-style id, so that is the only id the model
    reliably echoes.  Handed a 32-character chunk hash it copied the
    first one onto every fact instead.
    """
    return f"s{index}"


def _build_legacy_sentences(
    prepared: list[dict[str, Any]],
    normalised_texts: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Build the legacy sentence dicts and the label to chunk-id map.

    ``sentence_id`` is the short label the extractor speaks.  The real
    Neo4j chunk id travels alongside it, on the sentence and in the
    returned map, because that is what a :DOCUMENTS write must match.
    """
    sentences: list[dict[str, Any]] = []
    chunk_id_by_sentence_id: dict[str, str] = {}
    offset = 0
    for index, item in enumerate(prepared):
        text_raw = item["text_raw"]
        start, end, offset = _legacy_chunk_bounds(item["row"], text_raw, offset)
        label = chunk_sentence_label(index)
        chunk_id_by_sentence_id[label] = item["chunk_id"]
        sentences.append(
            {
                "sentence_id": label,
                "chunk_id": item["chunk_id"],
                "text": normalised_texts[index],
                "text_raw": text_raw,
                "start": start,
                "end": end,
            }
        )
    return sentences, chunk_id_by_sentence_id


def build_document_chunk_state(
    rows: list[dict[str, Any]],
    organization_id: str = "",
    resolve_schema: bool = True,
) -> dict[str, Any]:
    """Map Neo4j chunk rows to pipeline state (sentences + encounter_text).

    Set ``resolve_schema=False`` when the chunks are not a referral form
    bundle, so form recognition is not attempted.
    """
    prepared = _prepare_chunk_rows(rows)
    normalised_texts, schema_fields = _normalise_chunk_texts(
        [p["text_raw"] for p in prepared],
        organization_id=organization_id,
        resolve_schema=resolve_schema,
    )
    sentences, chunk_id_by_sentence_id = _build_legacy_sentences(
        prepared, normalised_texts
    )
    text_parts = [p["text_raw"] for p in prepared]

    # Every chunk, attachments included. This is the one coordinate space:
    # SpanResolver looks quotes up here, ConText decides the assertion here,
    # and lab-value recovery scans here. Anything shown to the model that is
    # missing from this string resolves to offset 0 -- the document banner --
    # and the assertion is then decided by the wrong text.
    encounter_text = CHUNK_TEXT_SEPARATOR.join(text_parts).strip()
    return {
        "sentences": sentences,
        "chunk_id_by_sentence_id": chunk_id_by_sentence_id,
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
) -> dict[str, Any]:
    if not chunk_ids:
        return {
            "sentences": [],
            "chunk_id_by_sentence_id": {},
            "encounter_text": "",
            "source_text": build_chunk_source_text([]),
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "errors": ["document_chunks mode requires non-empty chunk_ids"],
            **form_schema_state_fields("none"),
        }
    rows = client.run(GET_CHUNKS_BY_IDS, chunk_ids=chunk_ids)
    loaded = build_document_chunk_state(rows or [], organization_id=organization_id)
    if not loaded.get("sentences"):
        loaded["errors"] = ["no Chunk nodes found for supplied chunk_ids"]
    return loaded
