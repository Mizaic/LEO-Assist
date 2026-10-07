"""Apply per-document form recognition to a referral bundle's chunks.

Each recognised form is applied only to its own document's text. Every
other document gets the generic checkbox rules. A failed lookup of the
taught forms fails every document, so the run degrades and pauses; it is
never read as "no form was taught".

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6. Fail-closed boundary: DI-B7A69F26.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from libs.form_recognition.bundle import (
    Piece,
    chunk_pieces,
    split_chunks,
    split_documents,
)
from libs.form_recognition.recogniser import (
    Outcome,
    RecognitionFailed,
    Recognised,
    Unrecognised,
    recognise_bundle,
)
from libs.ner.form_checkbox_normalizer import normalize_form_checkbox_text
from libs.ner.form_layout_rules import apply_form_layout_rules
from libs.pipeline.form_coverage import measure_form_coverage
from libs.pipeline.form_schema_compose import (
    BoundDocument,
    hits_for_documents,
    is_ers_schema,
    sections_for_documents,
)
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    normalise_chunks_with_schema,
)
from libs.pipeline.form_schema_store import (
    MATCH_FAILED,
    MATCH_NOT_A_FORM,
    MATCH_RECOGNISED,
    MATCH_UNRECOGNISED,
    form_schema_state_fields,
    remember_schema,
)

logger = logging.getLogger(__name__)

PieceRef = tuple[int, int]


def recognise_texts(
    raw_texts: list[str], load_candidates: Callable[[], list[FormSchema]]
) -> list[Outcome]:
    """Recognise every document. A failed candidate lookup fails them all."""
    try:
        candidates = load_candidates()
    except Exception as exc:  # fail closed: degrade, never "not taught"
        logger.warning("taught form lookup failed", exc_info=True)
        return [
            RecognitionFailed(
                title=doc.title, chunk_indexes=doc.chunk_indexes, error=str(exc)
            )
            for doc in split_chunks(raw_texts)
        ]
    return recognise_bundle(raw_texts, candidates)


def bundle_match(outcomes: Sequence[Outcome]) -> str:
    """One word for the whole bundle; ``recognised`` only if nothing is open."""
    if not outcomes:
        return "none"
    if any(isinstance(o, RecognitionFailed) for o in outcomes):
        return MATCH_FAILED
    if any(isinstance(o, Unrecognised) for o in outcomes):
        return MATCH_UNRECOGNISED
    if any(isinstance(o, Recognised) for o in outcomes):
        return MATCH_RECOGNISED
    return MATCH_NOT_A_FORM


def _recognised(outcomes: Sequence[Outcome]) -> dict[int, FormSchema]:
    return {
        index: outcome.schema
        for index, outcome in enumerate(outcomes)
        if isinstance(outcome, Recognised) and outcome.schema is not None
    }


def primary_schema(outcomes: Sequence[Outcome]) -> FormSchema | None:
    """The specialty form if one was recognised, else the first recognised."""
    schemas = list(_recognised(outcomes).values())
    specialty = [schema for schema in schemas if not is_ers_schema(schema)]
    return (specialty or schemas or [None])[0]


def _keep_edges(original: str, rewritten: str) -> str:
    """Keep the piece's outer whitespace so document markers stay on a line."""
    if not original.strip():
        return original
    lead = original[: len(original) - len(original.lstrip())]
    trail = original[len(original.rstrip()) :]
    return f"{lead}{rewritten.strip()}{trail}"


def _refs_for(pieces: list[list[Piece]], doc: int) -> list[PieceRef]:
    return [
        (row_index, piece_index)
        for row_index, row in enumerate(pieces)
        for piece_index, (owner, _text) in enumerate(row)
        if owner == doc
    ]


def _section_map(schema: FormSchema, refs: list[PieceRef]) -> Any:
    """Use the taught chunk map only when this document's pieces are chunks 0..n."""
    if [row for row, _piece in refs] == list(range(len(refs))):
        return schema.chunk_section_map
    return None


def _document_texts(pieces: list[list[Piece]], refs: list[PieceRef]) -> list[str]:
    return [pieces[row][piece][1] for row, piece in refs]


def rewrite_chunks(raw_texts: list[str], outcomes: Sequence[Outcome]) -> list[str]:
    """Normalise each document with its own form, or with the generic rules."""
    pieces = chunk_pieces(raw_texts)
    taught: dict[PieceRef, str] = {}
    for doc, schema in _recognised(outcomes).items():
        if not schema.sections:
            continue
        refs = _refs_for(pieces, doc)
        texts = _document_texts(pieces, refs)
        rewritten = normalise_chunks_with_schema(
            schema, texts, _section_map(schema, refs)
        )
        for ref, text in zip(refs, rewritten):
            original = pieces[ref[0]][ref[1]][1]
            taught[ref] = _keep_edges(original, apply_form_layout_rules(text))
    return [
        "".join(
            _piece_text((row_index, piece_index), text, taught)
            for piece_index, (_owner, text) in enumerate(row)
        )
        for row_index, row in enumerate(pieces)
    ]


def _piece_text(ref: PieceRef, text: str, taught: dict[PieceRef, str]) -> str:
    if ref in taught:
        return taught[ref]
    return _keep_edges(text, normalize_form_checkbox_text(text))


def _bound_documents(
    raw_texts: list[str], outcomes: Sequence[Outcome]
) -> list[BoundDocument]:
    pieces = chunk_pieces(raw_texts)
    bound: list[BoundDocument] = []
    for doc, schema in _recognised(outcomes).items():
        refs = _refs_for(pieces, doc)
        texts = _document_texts(pieces, refs)
        bound.append(BoundDocument(schema, texts, _section_map(schema, refs)))
    return bound


def _taught_fields(
    raw_texts: list[str], outcomes: Sequence[Outcome], match: str
) -> dict[str, Any]:
    """Hits, sections, coverage and completeness from recognised documents."""
    bound = _bound_documents(raw_texts, outcomes)
    primary = primary_schema(outcomes)
    layout_ok = match == MATCH_RECOGNISED and primary is not None
    fields: dict[str, Any] = {"form_layout_matched": layout_ok}
    if not bound or primary is None:
        return fields
    fields["section_hits"] = hits_for_documents(bound, primary)
    fields["form_sections"] = sections_for_documents(bound, primary)
    own = [doc for doc in bound if doc.schema is primary]
    incomplete = any(
        measure_form_coverage(doc.schema, doc.texts, doc.chunk_section_map).incomplete
        for doc in own
    )
    fields["form_coverage_incomplete"] = incomplete
    if incomplete:
        fields["degraded"] = True
    if layout_ok and primary.completeness_groups:
        fields["completeness_groups"] = list(primary.completeness_groups)
    return fields


def _blank(text: str) -> str:
    return "".join(ch if ch == "\n" else " " for ch in text)


def document_scoped_text(
    text: str, recognition: Sequence[dict[str, Any]], fingerprint: str
) -> str:
    """Blank every document not recognised as *fingerprint*; keep offsets."""
    docs = [doc for doc in split_documents(text) if doc.text.strip()]
    if len(docs) != len(recognition):
        logger.warning(
            "form_recognition rows (%d) do not match documents (%d)",
            len(recognition),
            len(docs),
        )
        return text
    out = list(text)
    for doc, row in zip(docs, recognition):
        if row.get("outcome") == "recognised" and row.get("fingerprint") == fingerprint:
            continue
        start, end = doc.owned_start, doc.end
        out[start:end] = _blank(text[start:end])
    return "".join(out)


def recognition_fields(
    raw_texts: list[str], outcomes: Sequence[Outcome]
) -> dict[str, Any]:
    """Pipeline-state keys for a recognised (or not) referral bundle."""
    for schema in _recognised(outcomes).values():
        remember_schema(schema)
    match = bundle_match(outcomes)
    primary = primary_schema(outcomes)
    fields: dict[str, Any] = dict(
        form_schema_state_fields(
            match,
            primary.fingerprint if primary is not None else "none",
            (primary.form_name or "") if primary is not None else "",
        )
    )
    fields["form_recognition"] = [outcome.to_dict() for outcome in outcomes]
    fields.update(_taught_fields(raw_texts, outcomes, match))
    return fields
