"""Contract tests for the single text coordinate space (SourceText).

Atlas trace:
  VT: VT-SOURCE-TEXT-COORDINATE-SPACE
  DI: single coordinate space for extraction text offsets
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")

Every offset in the pipeline must index exactly one string.  These tests
pin that property at the contract level, independently of the loader.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.pipeline_contracts.text import (
    Deletion,
    RawChunk,
    Span,
    SpanOutOfRangeError,
    build_source_text,
)

SEPARATOR = "\n\n"


def _mid_cut_chunks() -> list[RawChunk]:
    """Three chunks where the removed region sits in the middle chunk."""
    return [
        RawChunk(chunk_id="alpha", text="Alpha section text."),
        RawChunk(chunk_id="beta", text="Keep this. REMOVE THIS. Keep that."),
        RawChunk(chunk_id="gamma", text="Gamma section text that must survive."),
    ]


def _remove_marker(raw: str) -> list[Deletion]:
    """Delete the literal 'REMOVE THIS. ' marker wherever it appears."""
    marker = "REMOVE THIS. "
    out: list[Deletion] = []
    start = raw.find(marker)
    while start != -1:
        out.append(
            Deletion(kind="test_marker", raw_start=start, raw_end=start + len(marker))
        )
        start = raw.find(marker, start + len(marker))
    return out


# ---------------------------------------------------------------------------
# Immutability and fail-closed reads
# ---------------------------------------------------------------------------


def test_source_text_is_frozen() -> None:
    source = build_source_text(_mid_cut_chunks(), separator=SEPARATOR)
    with pytest.raises(ValidationError):
        source.content = "tampered"
    with pytest.raises(ValidationError):
        source.segments = ()


def test_span_rejects_negative_and_inverted_bounds() -> None:
    with pytest.raises(ValidationError):
        Span(start=-1, end=4)
    with pytest.raises(ValidationError):
        Span(start=9, end=4)


def test_slice_outside_content_raises_rather_than_returning_empty() -> None:
    """Degradation must be represented, never inferred from an empty slice."""
    source = build_source_text(_mid_cut_chunks(), separator=SEPARATOR)
    beyond = len(source.content) + 1
    with pytest.raises(SpanOutOfRangeError):
        source.slice(Span(start=beyond, end=beyond + 5))
    with pytest.raises(SpanOutOfRangeError):
        source.slice(Span(start=0, end=beyond))


# ---------------------------------------------------------------------------
# The load-bearing property: offsets survive a mid-document deletion
# ---------------------------------------------------------------------------


def test_slice_matches_every_segment_including_those_after_a_mid_cut() -> None:
    """Offsets stay valid by construction, not by luck.

    Under the legacy design every offset past the cut point was invalid.
    Here each segment must slice back to exactly the origin chunk text it
    came from, including the two segments that follow the removed region.
    """
    chunks = _mid_cut_chunks()
    by_id = {c.chunk_id: c.text for c in chunks}
    source = build_source_text(chunks, separator=SEPARATOR, normalise=_remove_marker)

    assert "REMOVE THIS." not in source.content
    assert [s.origin_chunk_id for s in source.segments] == [
        "alpha",
        "beta",
        "beta",
        "gamma",
    ]

    for segment in source.segments:
        raw = by_id[segment.origin_chunk_id]
        expected = raw[
            segment.origin_offset : segment.origin_offset + segment.span.length
        ]
        assert source.slice(segment.span) == expected

    tail = source.segments[-1]
    assert tail.origin_chunk_id == "gamma"
    assert source.slice(tail.span) == "Gamma section text that must survive."


def test_segments_carry_origin_chunk_id_and_offset() -> None:
    chunks = _mid_cut_chunks()
    source = build_source_text(chunks, separator=SEPARATOR, normalise=_remove_marker)

    beta_segments = [s for s in source.segments if s.origin_chunk_id == "beta"]
    assert len(beta_segments) == 2
    assert source.slice(beta_segments[0].span) == "Keep this. "
    assert beta_segments[0].origin_offset == 0
    assert source.slice(beta_segments[1].span) == "Keep that."
    assert beta_segments[1].origin_offset == len("Keep this. REMOVE THIS. ")

    assert {s.origin_chunk_id for s in source.segments} == {"alpha", "beta", "gamma"}


def test_separator_text_belongs_to_no_segment() -> None:
    """Segments cover chunk content only, so provenance is never ambiguous."""
    source = build_source_text(_mid_cut_chunks(), separator=SEPARATOR)
    covered = sum(s.span.length for s in source.segments)
    assert covered == sum(len(c.text) for c in _mid_cut_chunks())
    assert covered < len(source.content)


# ---------------------------------------------------------------------------
# NormalisationRecord round-trip
# ---------------------------------------------------------------------------


def test_normalisation_record_maps_content_offset_back_to_raw() -> None:
    chunks = _mid_cut_chunks()
    raw = SEPARATOR.join(c.text for c in chunks)
    source = build_source_text(chunks, separator=SEPARATOR, normalise=_remove_marker)

    assert source.normalisation.raw_length == len(raw)
    assert len(source.normalisation.deletions) == 1

    for content_offset in range(len(source.content)):
        raw_offset = source.normalisation.to_raw_offset(content_offset)
        assert raw[raw_offset] == source.content[content_offset]


def test_normalisation_record_is_empty_when_nothing_is_removed() -> None:
    chunks = _mid_cut_chunks()
    source = build_source_text(chunks, separator=SEPARATOR)
    raw = SEPARATOR.join(c.text for c in chunks)

    assert source.content == raw
    assert source.normalisation.deletions == ()
    assert source.normalisation.to_raw_offset(17) == 17


def test_deletions_are_normalised_before_being_recorded() -> None:
    """Overlapping or unsorted deletions must not corrupt the coordinate space."""
    chunks = [RawChunk(chunk_id="only", text="ABCDEFGHIJ")]

    def _messy(_raw: str) -> list[Deletion]:
        return [
            Deletion(kind="b", raw_start=6, raw_end=8),
            Deletion(kind="a", raw_start=2, raw_end=5),
            Deletion(kind="a2", raw_start=3, raw_end=6),
        ]

    source = build_source_text(chunks, separator=SEPARATOR, normalise=_messy)
    assert source.content == "ABIJ"
    for segment in source.segments:
        expected = "ABCDEFGHIJ"[
            segment.origin_offset : segment.origin_offset + segment.span.length
        ]
        assert source.slice(segment.span) == expected


def test_chunk_removed_entirely_yields_no_segment() -> None:
    """A fully deleted chunk must vanish from segments, not alias another."""
    chunks = [
        RawChunk(chunk_id="keep", text="Kept."),
        RawChunk(chunk_id="gone", text="REMOVE THIS. "),
        RawChunk(chunk_id="after", text="After."),
    ]
    source = build_source_text(chunks, separator=SEPARATOR, normalise=_remove_marker)

    assert "gone" not in {s.origin_chunk_id for s in source.segments}
    after = [s for s in source.segments if s.origin_chunk_id == "after"][0]
    assert source.slice(after.span) == "After."
