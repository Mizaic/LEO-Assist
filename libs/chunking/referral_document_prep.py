"""LEO-compatible chunk ID helpers (ported from HCCP-Agents).

Source: HCCP-Agents/agent/leo_agents/services/referral_document_prep.py

The ID scheme matches ``libs.cypher.chunk_queries.make_chunk_id`` so
seeded local chunks stay compatible with the production pipeline.
"""

from __future__ import annotations

import hashlib
from typing import Any

from libs.chunking.markdown_page_chunker import MarkdownPageChunker

CHUNK_TEXT_SEPARATOR = "\n\n"
DEFAULT_CHUNK_TARGET_SIZE = 1000


def make_chunk_id(document_reference_id: str, ordinal: int, sha256: str) -> str:
    """Return a deterministic 32-char chunk id."""
    raw = f"{document_reference_id}:{ordinal}:{sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def chunk_sha256(text: str) -> str:
    """Return the SHA-256 hex digest of chunk text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_leo_chunk_records(
    document_reference_id: str,
    chunk_texts: list[str],
) -> list[dict[str, Any]]:
    """Build LEO chunk payloads with virtual concat offsets."""
    records: list[dict[str, Any]] = []
    offset = 0
    ordinal = 0
    for text in chunk_texts:
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        ordinal += 1
        digest = chunk_sha256(cleaned)
        char_end = offset + len(cleaned)
        records.append(
            {
                "chunk_id": make_chunk_id(document_reference_id, ordinal, digest),
                "document_reference_id": document_reference_id,
                "ordinal": ordinal,
                "sha256": digest,
                "text": cleaned,
                "char_start": offset,
                "char_end": char_end,
            }
        )
        offset = char_end + len(CHUNK_TEXT_SEPARATOR)
    return records


def chunk_markdown_text(
    markdown_text: str,
    *,
    target_size: int = DEFAULT_CHUNK_TARGET_SIZE,
) -> list[str]:
    """Chunk combined referral markdown without embeddings."""
    text = (markdown_text or "").strip()
    if not text:
        return []
    chunker = MarkdownPageChunker(text)
    document_chunks = chunker.extract_chunks_preserving_tables(
        target_size=target_size,
        source="referral_prep_chunk",
        max_table_rows=5,
    )
    if document_chunks:
        return [doc.page_content for doc in document_chunks if doc.page_content.strip()]
    return _paragraph_fallback(text, target_size)


def _paragraph_fallback(text: str, target_size: int) -> list[str]:
    """Split on blank lines when the table-preserving path is empty."""
    simple_chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > target_size and current:
            simple_chunks.append(current.strip())
            current = paragraph
        elif current:
            current = f"{current}\n\n{paragraph}"
        else:
            current = paragraph
    if current.strip():
        simple_chunks.append(current.strip())
    return simple_chunks
