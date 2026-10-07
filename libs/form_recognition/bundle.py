"""Split a referral bundle into its documents.

The converter joins documents with ``--- Document: {title} ---`` markers.
Stored chunks are cut by size, so one chunk can hold the end of one
document and the start of the next. Documents are therefore found in the
joined text, and each one records which chunks it came from.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

CHUNK_JOINER = "\n\n"

_DOC_HEADER_RE = re.compile(
    r"(---\s*Document:\s*(.+?)\s*---[ \t]*\n?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BundleDocument:
    """One document of a bundle, with its span in the joined text."""

    title: str
    text: str
    start: int
    end: int
    chunk_indexes: tuple[int, ...] = ()
    header_start: int = -1

    @property
    def owned_start(self) -> int:
        """Start of the span this document owns, marker line included."""
        return self.start if self.header_start < 0 else self.header_start


def split_documents(text: str) -> list[BundleDocument]:
    """Split *text* on document markers; text before the first is untitled."""
    text = text or ""
    matches = list(_DOC_HEADER_RE.finditer(text))
    if not matches:
        return [BundleDocument("", text, 0, len(text))]
    docs: list[BundleDocument] = []
    lead = matches[0].start()
    if text[:lead].strip():
        docs.append(BundleDocument("", text[:lead], 0, lead))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        title = match.group(2).strip()
        docs.append(
            BundleDocument(title, body, match.end(), end, header_start=match.start())
        )
    return docs


def _chunk_spans(chunks: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for chunk in chunks:
        spans.append((cursor, cursor + len(chunk)))
        cursor += len(chunk) + len(CHUNK_JOINER)
    return spans


def split_chunks(chunks: list[str]) -> list[BundleDocument]:
    """Join stored chunks, split into documents, and record chunk indexes."""
    spans = _chunk_spans(chunks)
    docs = split_documents(CHUNK_JOINER.join(chunks))
    placed: list[BundleDocument] = []
    for doc in docs:
        if not doc.text.strip():
            continue
        indexes = tuple(
            i
            for i, (start, end) in enumerate(spans)
            if start < doc.end and end > doc.start
        )
        placed.append(replace(doc, chunk_indexes=indexes))
    return placed


Piece = tuple[Optional[int], str]


def _cut_chunk(
    span: tuple[int, int], text: str, docs: list[BundleDocument]
) -> list[Piece]:
    """Cut one chunk into pieces owned by documents (or by nobody)."""
    start, end = span
    pieces: list[Piece] = []
    cursor = start
    for index, doc in enumerate(docs):
        lo, hi = max(cursor, doc.owned_start), min(end, doc.end)
        if lo >= hi:
            continue
        if lo > cursor:
            pieces.append((None, text[cursor - start : lo - start]))
        pieces.append((index, text[lo - start : hi - start]))
        cursor = hi
    if cursor < end:
        pieces.append((None, text[cursor - start :]))
    return pieces or [(None, text)]


def chunk_pieces(chunks: list[str]) -> list[list[Piece]]:
    """Cut each chunk at document boundaries.

    A piece's document index points into ``split_chunks(chunks)``. Text
    that belongs to no kept document (blank gaps) has index ``None``.
    Joining a chunk's pieces gives back the chunk exactly.
    """
    docs = split_chunks(chunks)
    return [
        _cut_chunk(span, chunk, docs)
        for span, chunk in zip(_chunk_spans(chunks), chunks)
    ]
