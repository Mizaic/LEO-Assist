"""The single text coordinate space for the extraction pipeline.

Atlas trace:
  DO: DO-728930A1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-728930A1")

Historically an extraction offset could index one of three different
strings: the form-schema normalised chunk text, the raw chunk
concatenation, or the PDF-stripped encounter text.  A guard slicing
``encounter_text[start:end]`` therefore returned the right span only by
luck.

``SourceText`` removes that class of defect by construction.  There is
exactly one string -- ``content`` -- and every offset indexes it.
Normalisation happens *inside* construction and records what it removed,
so offsets are remapped as the text is edited rather than being
invalidated after the fact.

This module is leaf-layer: it imports nothing from ``libs.pipeline``,
``libs.ner``, ``libs.pipeline_graph`` or ``libs.workflow``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, model_validator

CHUNK_SEPARATOR = "\n\n"


class SpanOutOfRangeError(ValueError):
    """Raised when a span does not lie inside the text it claims to index.

    Reading past the end of ``content`` is a defect, not a data
    condition.  Failing closed keeps the degradation visible instead of
    letting a caller infer "nothing found" from an empty string.
    """


class Span(BaseModel):
    """A half-open ``[start, end)`` window over a ``SourceText.content``."""

    model_config = ConfigDict(frozen=True)

    start: int
    end: int

    @model_validator(mode="after")
    def _check_bounds(self) -> Span:
        if self.start < 0:
            raise ValueError(f"span start must be >= 0, got {self.start}")
        if self.end < self.start:
            raise ValueError(f"span end {self.end} precedes start {self.start}")
        return self

    @property
    def length(self) -> int:
        return self.end - self.start


class TextSegment(BaseModel):
    """A run of ``content`` that survived normalisation, with its origin.

    ``origin_offset`` is the offset inside the origin chunk's raw text at
    which this run begins, so a fact found in ``content`` can still be
    attributed to the Neo4j :Chunk it came from.  A chunk split by an
    interior deletion produces more than one segment.
    """

    model_config = ConfigDict(frozen=True)

    span: Span
    origin_chunk_id: str
    origin_offset: int

    @model_validator(mode="after")
    def _check_origin(self) -> TextSegment:
        if self.origin_offset < 0:
            raise ValueError(f"origin_offset must be >= 0, got {self.origin_offset}")
        return self


class Deletion(BaseModel):
    """A half-open ``[raw_start, raw_end)`` range removed during construction."""

    model_config = ConfigDict(frozen=True)

    kind: str
    raw_start: int
    raw_end: int


class NormalisationRecord(BaseModel):
    """What construction removed from the raw concatenation, and where.

    Deletions are stored sorted, non-overlapping and clipped to the raw
    text, which is what makes :meth:`to_raw_offset` a total function.
    """

    model_config = ConfigDict(frozen=True)

    raw_length: int
    deletions: tuple[Deletion, ...] = ()

    @property
    def content_length(self) -> int:
        removed = sum(d.raw_end - d.raw_start for d in self.deletions)
        return self.raw_length - removed

    def to_raw_offset(self, content_offset: int) -> int:
        """Map an offset in ``content`` back to the raw concatenation."""
        if content_offset < 0 or content_offset > self.content_length:
            raise SpanOutOfRangeError(
                f"content offset {content_offset} outside "
                f"[0, {self.content_length}]"
            )
        raw_offset = content_offset
        for deletion in self.deletions:
            if deletion.raw_start > raw_offset:
                break
            raw_offset += deletion.raw_end - deletion.raw_start
        return raw_offset


class RawChunk(BaseModel):
    """A source chunk exactly as stored in Neo4j, before any normalisation."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    text: str


class SourceText(BaseModel):
    """Immutable. The ONE coordinate space. Offsets index ``content`` only."""

    model_config = ConfigDict(frozen=True)

    content: str
    segments: tuple[TextSegment, ...] = ()
    normalisation: NormalisationRecord

    @model_validator(mode="after")
    def _check_segments_fit(self) -> SourceText:
        limit = len(self.content)
        for segment in self.segments:
            if segment.span.end > limit:
                raise ValueError(
                    f"segment for chunk {segment.origin_chunk_id} ends at "
                    f"{segment.span.end}, past content length {limit}"
                )
        return self

    def slice(self, span: Span) -> str:
        """Return the window ``span`` names. The only sanctioned read."""
        if span.end > len(self.content):
            raise SpanOutOfRangeError(
                f"span [{span.start}, {span.end}) outside content "
                f"of length {len(self.content)}"
            )
        return self.content[span.start : span.end]


Normaliser = Callable[[str], Sequence[Deletion]]


def _clean_deletions(
    deletions: Sequence[Deletion], raw_length: int
) -> tuple[Deletion, ...]:
    """Clip, sort and merge deletions so the offset arithmetic stays total."""
    clipped: list[Deletion] = []
    for deletion in deletions:
        start = max(0, min(int(deletion.raw_start), raw_length))
        end = max(0, min(int(deletion.raw_end), raw_length))
        if end > start:
            clipped.append(Deletion(kind=deletion.kind, raw_start=start, raw_end=end))
    clipped.sort(key=lambda d: (d.raw_start, d.raw_end))

    merged: list[Deletion] = []
    for deletion in clipped:
        if merged and deletion.raw_start <= merged[-1].raw_end:
            previous = merged[-1]
            kinds = previous.kind.split("+")
            if deletion.kind not in kinds:
                kinds.append(deletion.kind)
            merged[-1] = Deletion(
                kind="+".join(kinds),
                raw_start=previous.raw_start,
                raw_end=max(previous.raw_end, deletion.raw_end),
            )
        else:
            merged.append(deletion)
    return tuple(merged)


def _survivals(
    raw_length: int, deletions: Sequence[Deletion]
) -> list[tuple[int, int, int]]:
    """Return ``(raw_start, raw_end, content_start)`` for each surviving run."""
    runs: list[tuple[int, int, int]] = []
    cursor = 0
    content_start = 0
    for deletion in deletions:
        if deletion.raw_start > cursor:
            runs.append((cursor, deletion.raw_start, content_start))
            content_start += deletion.raw_start - cursor
        cursor = max(cursor, deletion.raw_end)
    if cursor < raw_length:
        runs.append((cursor, raw_length, content_start))
    return runs


def _chunk_ranges(
    chunks: Sequence[RawChunk], separator: str
) -> list[tuple[RawChunk, int, int]]:
    """Return each chunk's ``[start, end)`` range in the raw concatenation."""
    ranges: list[tuple[RawChunk, int, int]] = []
    cursor = 0
    for index, chunk in enumerate(chunks):
        if index:
            cursor += len(separator)
        ranges.append((chunk, cursor, cursor + len(chunk.text)))
        cursor += len(chunk.text)
    return ranges


def _build_segments(
    chunks: Sequence[RawChunk],
    separator: str,
    survivals: Sequence[tuple[int, int, int]],
) -> tuple[TextSegment, ...]:
    """Intersect each chunk with the surviving runs, in content coordinates."""
    segments: list[TextSegment] = []
    for chunk, chunk_start, chunk_end in _chunk_ranges(chunks, separator):
        for run_start, run_end, content_start in survivals:
            low = max(chunk_start, run_start)
            high = min(chunk_end, run_end)
            if high <= low:
                continue
            span_start = content_start + (low - run_start)
            segments.append(
                TextSegment(
                    span=Span(start=span_start, end=span_start + (high - low)),
                    origin_chunk_id=chunk.chunk_id,
                    origin_offset=low - chunk_start,
                )
            )
    return tuple(segments)


def build_source_text(
    chunks: Sequence[RawChunk],
    *,
    separator: str = CHUNK_SEPARATOR,
    normalise: Normaliser | None = None,
) -> SourceText:
    """Build the one coordinate space from ordered raw chunks.

    Args:
        chunks: Source chunks in document order.
        separator: Text joined between adjacent chunks. Separator text
            belongs to no chunk and therefore to no segment.
        normalise: Returns the ranges to remove from the raw
            concatenation. Offsets are remapped around those ranges, so
            every segment stays valid including after a mid-document cut.

    Returns:
        A frozen ``SourceText`` whose ``content`` is the normalised text.
    """
    raw = separator.join(chunk.text for chunk in chunks)
    deletions = _clean_deletions(list(normalise(raw)) if normalise else [], len(raw))
    survivals = _survivals(len(raw), deletions)
    content = "".join(raw[start:end] for start, end, _ in survivals)
    return SourceText(
        content=content,
        segments=_build_segments(chunks, separator, survivals),
        normalisation=NormalisationRecord(raw_length=len(raw), deletions=deletions),
    )
