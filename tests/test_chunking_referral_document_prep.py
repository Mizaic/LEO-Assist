"""Unit tests for libs/chunking referral document prep.

Atlas trace:
  VT: VT-3FE08AC5
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-3FE08AC5")

Ported from HCCP-Agents referral_document_prep tests. Confirms the
copied chunker produces LEO-compatible chunk records without
langchain and without writing to Neo4j.
"""

from __future__ import annotations

from libs.chunking.referral_document_prep import (
    build_leo_chunk_records,
    chunk_markdown_text,
    make_chunk_id,
)
from libs.cypher.chunk_queries import make_chunk_id as neo4j_make_chunk_id


def test_make_chunk_id_is_deterministic() -> None:
    doc_id = "ref-1:leo-referral-bundle"
    digest = "abc123"
    assert make_chunk_id(doc_id, 1, digest) == make_chunk_id(doc_id, 1, digest)


def test_make_chunk_id_matches_neo4j_helper() -> None:
    doc_id = "dr-1"
    digest = "abc123"
    assert make_chunk_id(doc_id, 1, digest) == neo4j_make_chunk_id(doc_id, 1, digest)


def test_build_leo_chunk_records_preserves_table_text() -> None:
    table = "| Test | Value |\n| Hb | 120 |"
    records = build_leo_chunk_records("dr-1", [table])
    assert len(records) == 1
    assert "| Hb |" in records[0]["text"]
    assert records[0]["char_end"] > records[0]["char_start"]


def test_chunk_markdown_text_preserves_table_rows() -> None:
    markdown = "# Labs\n\n| WBC | 5.2 |\n| RBC | 4.1 |"
    chunks = chunk_markdown_text(markdown, target_size=200)
    joined = "\n".join(chunks)
    assert "| WBC |" in joined or "| RBC |" in joined


def test_chunk_markdown_text_empty_returns_empty() -> None:
    assert chunk_markdown_text("   ") == []


def test_chunk_markdown_text_splits_large_blocks() -> None:
    first = "Alpha paragraph. " * 40
    second = "Beta paragraph. " * 40
    markdown = f"{first.strip()}\n\n{second.strip()}"
    chunks = chunk_markdown_text(markdown, target_size=200)
    assert len(chunks) >= 2
