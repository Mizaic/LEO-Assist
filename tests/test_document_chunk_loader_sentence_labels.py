"""Chunk sentences need the short label the extractor was taught to echo.

Every one of the few-shot examples in ``libs/prompts/extraction_examples.py``
answers with ``"sentence_id": "s0"``. The document-chunks loader handed the
model a 32-character Neo4j chunk hash instead, so the model kept answering
``s0`` anyway. No sentence had that id, the write fell back to matching by
character offset, and all 13 facts on the reference Sherwood referral landed
on the document banner with no evidence offsets at all.

The loader must therefore speak the same language as the prompt: label each
chunk ``s0, s1, s2, ...`` in chunk order, and keep a complete reverse map so
the graph write can still find the real :Chunk node behind each label.

Atlas trace:
  DI: DI-16CE412B, DI-B7A69F26  (fail-closed boundary)
  DO: DO-728930A1
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.document_chunk_loader import build_document_chunk_state

_BANNER = "b689f4e037be32adc8f70163067c0063"
_HISTORY = "4a8d9afbdb1e46b4caedb0aadcdbece1"
_EXAM = "a2c3d4e5f6071819a0b1c2d3e4f50607"

_TEXTS = {
    _BANNER: "--- Document: Sherwood 2WW gynae referral.doc ---",
    _HISTORY: "Reason for referral: post-menopausal bleeding for six weeks.",
    _EXAM: "On examination: abdo full soft, non tender.",
}


def _rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    for ordinal, chunk_id in enumerate((_BANNER, _HISTORY, _EXAM)):
        text = _TEXTS[chunk_id]
        rows.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "ordinal": ordinal,
                "char_start": offset,
                "char_end": offset + len(text),
            }
        )
        offset += len(text) + 2
    return rows


def _state() -> dict[str, Any]:
    return build_document_chunk_state(_rows())


def test_chunks_are_labelled_in_chunk_order() -> None:
    """The label order must follow the document, not the hash order."""
    labels = [s["sentence_id"] for s in _state()["sentences"]]
    assert labels == ["s0", "s1", "s2"]


def test_the_state_carries_a_reverse_map_to_the_real_chunk_ids() -> None:
    state = _state()
    assert state.get("chunk_id_by_sentence_id") == {
        "s0": _BANNER,
        "s1": _HISTORY,
        "s2": _EXAM,
    }


def test_every_sentence_label_is_in_the_reverse_map() -> None:
    """A label with no chunk behind it cannot be written to the graph."""
    state = _state()
    reverse = state.get("chunk_id_by_sentence_id") or {}
    missing = [
        s["sentence_id"] for s in state["sentences"] if s["sentence_id"] not in reverse
    ]
    assert missing == [], f"labels with no chunk behind them: {missing}"


def test_no_two_labels_share_a_chunk_id() -> None:
    """Two labels on one chunk would attribute a fact to the wrong text."""
    reverse = _state().get("chunk_id_by_sentence_id") or {}
    assert len(set(reverse.values())) == len(reverse)


def test_relabelling_leaves_the_sentence_text_and_offsets_alone() -> None:
    """Only the id changes. The text and the coordinates must not move."""
    sentences = _state()["sentences"]
    for sentence, row in zip(sentences, _rows()):
        assert sentence["text"] == row["text"]
        assert sentence["text_raw"] == row["text"]
        assert sentence["start"] == row["char_start"]
        assert sentence["end"] == row["char_end"]


def test_encounter_text_is_unchanged_by_relabelling() -> None:
    """The banner-stripped bundle text is a separate concern."""
    state = _state()
    assert _TEXTS[_HISTORY] in state["encounter_text"]
    assert _TEXTS[_EXAM] in state["encounter_text"]


def test_source_text_still_maps_back_to_the_real_chunk_ids() -> None:
    """SourceText is keyed on the Neo4j id, not on the model-facing label."""
    source_text = _state()["source_text"]
    origins = [segment.origin_chunk_id for segment in source_text.segments]
    assert origins == [_BANNER, _HISTORY, _EXAM]


def test_a_single_chunk_bundle_is_labelled_s0() -> None:
    state = build_document_chunk_state(_rows()[1:2])
    assert state["sentences"][0]["sentence_id"] == "s0"
    assert state["chunk_id_by_sentence_id"] == {"s0": _HISTORY}


def test_an_empty_bundle_still_carries_an_empty_reverse_map() -> None:
    """Callers must not have to guess whether the key is there."""
    state = build_document_chunk_state([])
    assert state.get("chunk_id_by_sentence_id") == {}
