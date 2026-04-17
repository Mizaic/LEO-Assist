"""VT-LEO-AI-179: :Chunk node and Encounter|Chunk DOCUMENTS source.

Verifies DI-LEO-AI-185 acceptance criteria:
- :Chunk node deterministic ID is stable across re-ingestion
- ``_build_upsert_query`` accepts source_label in {"Encounter", "Chunk"}
- The Chunk variant uses an OPTIONAL MATCH for the patient shortcut so
  documents written from chunks under a freshly-loaded DocumentReference
  do not fail when no Patient->DocumentReference link exists yet
- The query rejects unknown source labels
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.cypher.chunk_queries import (
    chunk_sha256,
    make_chunk_id,
    upsert_chunk_payload,
)
from libs.cypher.documents_queries import _build_upsert_query


def test_chunk_id_is_deterministic_and_stable() -> None:
    text = "Patient reports new chest pain."
    sha = chunk_sha256(text)
    cid = make_chunk_id("dr-1", 0, sha)
    again = make_chunk_id("dr-1", 0, sha)
    other = make_chunk_id("dr-1", 1, sha)

    assert cid == again, "deterministic id required for idempotent ingestion"
    assert cid != other, "different ordinals must produce different ids"
    assert len(cid) == 32


def test_upsert_chunk_payload_writes_with_expected_kwargs() -> None:
    session = MagicMock()
    cid = upsert_chunk_payload(
        document_reference_id="dr-77",
        ordinal=2,
        text="Hello world.",
        char_start=10,
        char_end=22,
        session=session,
    )
    session.run.assert_called_once()
    kwargs = session.run.call_args.kwargs
    assert kwargs["document_reference_id"] == "dr-77"
    assert kwargs["ordinal"] == 2
    assert kwargs["char_start"] == 10
    assert kwargs["char_end"] == 22
    assert kwargs["text"] == "Hello world."
    assert kwargs["chunk_id"] == cid
    assert kwargs["sha256"] == chunk_sha256("Hello world.")


def test_build_upsert_query_encounter_path_uses_has_encounter() -> None:
    q = _build_upsert_query(
        "Clinical_finding", "HAS_FINDING", source_label="Encounter"
    )
    assert "MATCH (src:Encounter {id: $source_id})" in q
    assert "<-[:HAS_ENCOUNTER]-(p:Patient)" in q
    assert "MERGE (src)-[r:DOCUMENTS" in q


def test_build_upsert_query_chunk_path_uses_optional_match() -> None:
    q = _build_upsert_query(
        "Clinical_finding", "HAS_FINDING", source_label="Chunk"
    )
    assert "MATCH (src:Chunk {id: $source_id})" in q
    assert "OPTIONAL MATCH" in q, "patient shortcut must be optional for chunks"
    assert "MERGE (src)-[r:DOCUMENTS" in q
    assert "p IS NOT NULL" in q, "FOREACH must skip when patient missing"


def test_build_upsert_query_rejects_unknown_source_label() -> None:
    with pytest.raises(ValueError):
        _build_upsert_query("Clinical_finding", "HAS_FINDING", source_label="Foo")
