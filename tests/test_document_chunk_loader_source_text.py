"""Loader integration for the single text coordinate space.

Atlas trace:
  VT: VT-SOURCE-TEXT-COORDINATE-SPACE
  DO: DO-728930A1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")

The loader must publish a SourceText alongside the legacy state fields,
without changing a single byte of that legacy state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from libs.pipeline.document_chunk_loader import (
    CHUNK_TEXT_SEPARATOR,
    build_document_chunk_state,
    bundle_trim_deletions,
)
from libs.pipeline_contracts.text import SourceText

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)

SECTION_C_MARKERS = (
    "vaginal discharge",
    "no vaginal itch/dryness",
    "no pelvic pain",
)

_DOC_CHUNK = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n"
    "Section A: cancer type suspected\nCervix [ ] Ovary [ ]"
)
_PDF_CHUNK = (
    "--- Document: Clinical Information.pdf ---\n"
    "NHS Confidential\nClinical Information Summary\nNo information provided"
)
_TAIL_CHUNK = "Section D: investigations performed\nUltrasound [X]"


def _sherwood_chunk_texts() -> list[str]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [c["text"] for c in data["chunks"]]


def _rows(texts: list[str], *, supply_offsets: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    for index, text in enumerate(texts):
        row: dict[str, Any] = {
            "chunk_id": f"chunk-{index}",
            "text": text,
            "ordinal": index,
            "char_start": offset if supply_offsets else None,
            "char_end": offset + len(text) if supply_offsets else None,
        }
        offset += len(text) + len(CHUNK_TEXT_SEPARATOR)
        rows.append(row)
    return rows


def _build(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build loader state with the form-schema lookup stubbed out."""
    with patch(
        "libs.pipeline.document_chunk_loader._resolve_chunk_schema",
        return_value=(None, {}),
    ):
        return build_document_chunk_state(rows)


# ---------------------------------------------------------------------------
# Byte-identical legacy behaviour
# ---------------------------------------------------------------------------


def test_bundle_trim_deletions_reproduce_the_encounter_text() -> None:
    """The deletion ranges must rebuild exactly what extraction reads.

    Extraction reads the whole bundle now, so the only difference between
    the raw join and ``encounter_text`` is the outer whitespace.
    """
    samples = [
        "",
        "No attachment here at all.",
        _DOC_CHUNK + CHUNK_TEXT_SEPARATOR + _PDF_CHUNK,
        "  leading and trailing whitespace  ",
        "   ",
        "GP Form content\n\n--- Document: report.PDF ---\nAdmin noise",
        CHUNK_TEXT_SEPARATOR.join(_sherwood_chunk_texts()),
    ]
    for raw in samples:
        kept: list[str] = []
        cursor = 0
        for deletion in bundle_trim_deletions(raw):
            kept.append(raw[cursor : deletion.raw_start])  # noqa: E203
            cursor = deletion.raw_end
        kept.append(raw[cursor:])
        assert "".join(kept) == raw.strip()


def test_legacy_state_fields_are_byte_identical_when_source_text_ignored() -> None:
    texts = _sherwood_chunk_texts()
    state = _build(_rows(texts, supply_offsets=False))

    legacy = {k: v for k, v in state.items() if k != "source_text"}
    expected_encounter = CHUNK_TEXT_SEPARATOR.join(texts).strip()

    assert legacy["encounter_text"] == expected_encounter
    assert len(legacy["sentences"]) == len(texts)
    for index, sentence in enumerate(legacy["sentences"]):
        # sentence_id is the short label the extractor echoes; the Neo4j
        # chunk id it stands for rides alongside it and in the reverse map.
        assert sentence["sentence_id"] == f"s{index}"
        assert sentence["chunk_id"] == f"chunk-{index}"
        assert legacy["chunk_id_by_sentence_id"][f"s{index}"] == f"chunk-{index}"
        assert sentence["text_raw"] == texts[index]
    assert legacy["text_segmentation_mode"] == "document_chunks"


# ---------------------------------------------------------------------------
# The two-meanings-of-one-field defect
# ---------------------------------------------------------------------------


def test_source_text_identical_whether_or_not_rows_supply_offsets() -> None:
    """One coordinate space: the database row must not change the answer."""
    texts = _sherwood_chunk_texts()
    without = _build(_rows(texts, supply_offsets=False))["source_text"]
    with_offsets = _build(_rows(texts, supply_offsets=True))["source_text"]

    assert isinstance(without, SourceText)
    assert without == with_offsets


def test_source_text_ignores_document_absolute_row_offsets() -> None:
    """Absolute Neo4j offsets are a different space and must not leak in."""
    texts = _sherwood_chunk_texts()
    rows = _rows(texts, supply_offsets=True)
    shift = 5000
    for row in rows:
        row["char_start"] += shift
        row["char_end"] += shift

    source = _build(rows)["source_text"]
    baseline = _build(_rows(texts, supply_offsets=False))["source_text"]
    assert source == baseline
    assert source.segments[0].span.start == 0


def test_legacy_offsets_survive_an_attachment_in_the_middle() -> None:
    """Offsets stay usable now nothing is cut out of the middle.

    This test used to assert the opposite, pinning the defect: removing the
    PDF section from the middle left every later sentence's offsets pointing
    past the end, so ``encounter_text[start:end]`` silently returned "".
    A chunk after the attachment could not be located at all.
    """
    rows = _rows([_DOC_CHUNK, _PDF_CHUNK, _TAIL_CHUNK], supply_offsets=False)
    state = _build(rows)
    encounter_text = state["encounter_text"]
    tail = state["sentences"][2]

    assert tail["text_raw"] == _TAIL_CHUNK
    assert encounter_text[tail["start"] : tail["end"]] == _TAIL_CHUNK  # noqa: E203


# ---------------------------------------------------------------------------
# Sherwood regression anchor
# ---------------------------------------------------------------------------


def test_sherwood_every_segment_slices_back_to_its_origin_chunk() -> None:
    texts = _sherwood_chunk_texts()
    source: SourceText = _build(_rows(texts, supply_offsets=False))["source_text"]

    assert source.segments
    for segment in source.segments:
        index = int(segment.origin_chunk_id.split("-")[1])
        raw = texts[index]
        expected = raw[
            segment.origin_offset : segment.origin_offset + segment.span.length
        ]
        assert source.slice(segment.span) == expected


def test_sherwood_section_c_narrative_survives_into_source_text() -> None:
    """An 815-character Section C narrative was once silently discarded."""
    texts = _sherwood_chunk_texts()
    source: SourceText = _build(_rows(texts, supply_offsets=False))["source_text"]

    for marker in SECTION_C_MARKERS:
        assert marker in source.content, marker

    section_c = [t for t in texts if "Section C: Further Clinical details" in t][0]
    segments = [
        s
        for s in source.segments
        if s.origin_chunk_id == f"chunk-{texts.index(section_c)}"
    ]
    assert len(segments) == 1
    assert source.slice(segments[0].span) == section_c


def test_sherwood_attachment_survives_into_source_text() -> None:
    """The attachment is part of the coordinate space, not a deletion.

    This test used to require the wrapper be recorded as a deletion and
    absent from ``content``. That was the coordinate-space split: the model
    was shown the attachment while the resolver could not see it.
    """
    texts = _sherwood_chunk_texts()
    source: SourceText = _build(_rows(texts, supply_offsets=False))["source_text"]
    raw = CHUNK_TEXT_SEPARATOR.join(texts)

    assert source.normalisation.raw_length == len(raw)
    assert "Clinical Information" in source.content
    for content_offset in range(0, len(source.content), 37):
        raw_offset = source.normalisation.to_raw_offset(content_offset)
        assert raw[raw_offset] == source.content[content_offset]


def test_source_text_content_matches_legacy_encounter_text() -> None:
    """content is the encounter_text guards already read -- one space, not two."""
    texts = _sherwood_chunk_texts()
    state = _build(_rows(texts, supply_offsets=False))
    assert state["source_text"].content == state["encounter_text"]
