"""Sentence IDs on the document-chunks path must be short labels (s0, s1, ...).

Bug: _build_legacy_sentences was assigning the 32-char chunk hash as
sentence_id. The LLM is primed on few-shot examples that use s0/s1-style
labels. When it receives hashes it copies the first hash for every entity,
causing SpanResolver to search the wrong chunk window.

Fix: assign s0, s1, ... in chunk ordinal order and expose a reverse lookup
(chunk_id_by_sentence_id) in pipeline state so downstream code can recover
the original Neo4j chunk id when needed.

Atlas trace: DI-16CE412B / DO-728930A1
"""

from __future__ import annotations

import re

from libs.pipeline.document_chunk_loader import build_document_chunk_state

_CHUNK_HASH_RE = re.compile(r"^[0-9a-f]{32}$")

_ROWS = [
    {
        "chunk_id": "b689f4e037be32adc8f70163067c0063",
        "text": "Reason for referral: chest pain on exertion.",
        "ordinal": 0,
        "char_start": 0,
        "char_end": 44,
    },
    {
        "chunk_id": "a2c3d4e5f6071819a0b1c2d3e4f50607",
        "text": "Past medical history: hypertension.",
        "ordinal": 1,
        "char_start": 44,
        "char_end": 79,
    },
]


def test_sentence_ids_are_short_labels_not_hashes() -> None:
    """sentence_id for each chunk must be s0, s1, ... not a 32-char hash."""
    state = build_document_chunk_state(_ROWS)
    sentences = state["sentences"]
    assert len(sentences) == 2

    assert sentences[0]["sentence_id"] == "s0", (
        f"Expected 's0', got '{sentences[0]['sentence_id']}' -- "
        "sentence_id must be the short label, not the chunk hash"
    )
    assert sentences[1]["sentence_id"] == "s1"


def test_sentence_ids_are_never_chunk_hashes() -> None:
    """No sentence_id should look like a 32-character hex string."""
    state = build_document_chunk_state(_ROWS)
    for sent in state["sentences"]:
        sid = sent["sentence_id"]
        assert not _CHUNK_HASH_RE.match(sid), (
            f"sentence_id '{sid}' looks like a chunk hash -- "
            "use short s0/s1/... labels instead"
        )


def test_reverse_lookup_maps_sid_to_chunk_id() -> None:
    """chunk_id_by_sentence_id must map s0 -> original hash, s1 -> original hash."""
    state = build_document_chunk_state(_ROWS)
    reverse = state.get("chunk_id_by_sentence_id")
    assert reverse is not None, "state must include 'chunk_id_by_sentence_id'"
    assert reverse["s0"] == "b689f4e037be32adc8f70163067c0063"
    assert reverse["s1"] == "a2c3d4e5f6071819a0b1c2d3e4f50607"


def test_single_chunk_gets_s0_label() -> None:
    """A single-chunk referral should have sentence_id 's0'."""
    row = {
        "chunk_id": "deadbeef" * 4,
        "text": "Single chunk text.",
        "ordinal": 0,
        "char_start": 0,
        "char_end": 18,
    }
    state = build_document_chunk_state([row])
    assert state["sentences"][0]["sentence_id"] == "s0"
