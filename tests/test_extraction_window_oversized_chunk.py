"""An oversized chunk must be split across windows, never truncated away.

HCCP does not guarantee a chunk fits an extraction window. Production
referral 000481858468 arrives as 16 chunks where one holds 38,778 of the
59,592 characters -- 65% of the referral in a single chunk, carrying the
blood panel and the examination narrative.

``plan_extraction_windows_by_tokens`` used to emit that chunk alone with
``truncated=True``, and the caller then cut it to half the window budget.
Measured against production: 6,780 characters (11% of the referral) were
dropped at a 16,000-token budget and 22,780 (38%) at 8,000. Nothing in the
run said so -- a count landed in ``extraction_window_truncated_count``,
which is a metric, not a warning.

Splitting costs one extra model call. Truncating costs the bottom third of
a cancer referral.

Atlas trace:
  DI: DI-B5C78811, DI-B7A69F26
  DO: DO-292D7D75
"""

from __future__ import annotations

from libs.pipeline.extraction_window import (
    ChunkRef,
    plan_extraction_windows_by_tokens,
    window_chunk_text,
)

# 200 numbered lines. Line boundaries matter: a split must land on one so a
# lab result and its value are not severed mid-number.
_BIG_LINES = [
    f"Line {n:03d}: serum analyte {n} result {n}.{n % 10} umol/L" for n in range(200)
]
_BIG_CHUNK = "\n".join(_BIG_LINES)
_SMALL = "Section A: cancer type suspected\nCervix [X]"


def _plan(chunks: list[ChunkRef], budget: int):
    return plan_extraction_windows_by_tokens(
        chunks,
        max_window_input_tokens=budget,
        window_overlap_chunks=1,
        max_chunks_per_window=10,
    )


def _text_seen_by_model(windows, chunks: list[ChunkRef]) -> str:
    """Concatenate every slice of text the planner actually hands over."""
    by_id = {c.chunk_id: c.text for c in chunks}
    seen: list[str] = []
    for window in windows:
        for chunk_id in window.chunk_ids:
            seen.append(window_chunk_text(window, chunk_id, by_id[chunk_id]))
    return "\n".join(seen)


def test_oversized_chunk_is_not_marked_truncated() -> None:
    """Splitting replaces truncation, so nothing claims to have been cut."""
    chunks = [ChunkRef(chunk_id="big", text=_BIG_CHUNK)]
    windows = _plan(chunks, 2000)

    assert len(windows) > 1, "an oversized chunk must span several windows"
    assert not any(w.truncated for w in windows)


def test_every_line_of_an_oversized_chunk_reaches_a_window() -> None:
    """The whole point: no clinical line is silently dropped."""
    chunks = [ChunkRef(chunk_id="big", text=_BIG_CHUNK)]
    seen = _text_seen_by_model(_plan(chunks, 2000), chunks)

    missing = [line for line in _BIG_LINES if line not in seen]
    assert not missing, f"{len(missing)} lines never reached a window: {missing[:3]}"


def test_split_lands_on_line_boundaries() -> None:
    """A result must not be severed from its value by a window edge."""
    chunks = [ChunkRef(chunk_id="big", text=_BIG_CHUNK)]
    for window in _plan(chunks, 2000):
        slice_text = window_chunk_text(window, "big", _BIG_CHUNK)
        for line in slice_text.strip().split("\n"):
            assert line in _BIG_LINES, f"partial line at a window edge: {line!r}"


def test_oversized_chunk_alongside_normal_chunks_loses_nothing() -> None:
    """The real shape of 000481858468: one huge chunk among small ones."""
    chunks = [
        ChunkRef(chunk_id="c0", text=_SMALL),
        ChunkRef(chunk_id="big", text=_BIG_CHUNK),
        ChunkRef(chunk_id="c2", text="Section D: investigations\nUltrasound [X]"),
    ]
    seen = _text_seen_by_model(_plan(chunks, 2000), chunks)

    for line in _BIG_LINES:
        assert line in seen, line
    assert "Section A: cancer type suspected" in seen
    assert "Section D: investigations" in seen


def test_normal_chunks_are_unaffected_by_the_split_path() -> None:
    """A bundle that already fits must plan exactly as it did before."""
    chunks = [ChunkRef(chunk_id=f"c{i}", text=_SMALL) for i in range(4)]
    windows = _plan(chunks, 16000)

    assert len(windows) == 1
    assert windows[0].chunk_ids == ("c0", "c1", "c2", "c3")
    assert window_chunk_text(windows[0], "c0", _SMALL) == _SMALL


def test_window_chunk_text_returns_whole_text_when_not_sliced() -> None:
    """The helper is safe to call unconditionally on every window."""
    chunks = [ChunkRef(chunk_id="c0", text=_SMALL)]
    window = _plan(chunks, 16000)[0]
    assert window_chunk_text(window, "c0", _SMALL) == _SMALL
