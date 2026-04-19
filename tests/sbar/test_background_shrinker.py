"""VT-LEO-AI-514 TC-001 / TC-002: Background prompt shrinker.

Verifies the shrinker:
  - Is a no-op under budget (TC-001).
  - Applies progressive per-source caps before dropping sources (TC-002).
  - Drops sources only at the smallest cap (TC-002).
  - Always keeps at least one source when sources are non-empty.
  - Builds a plain-English notice when trimming happens.

See DI-LEO-AI-513 / DO-LEO-AI-515.
"""

from __future__ import annotations

import pytest

from libs.sbar.background_shrinker import (
    _PROGRESSIVE_CAPS,
    ShrinkReport,
    shrink_background_context,
)
from libs.sbar.source_resolver import ResolvedSource


def _make_source(idx: int, *, text_len: int) -> ResolvedSource:
    return ResolvedSource(
        source_label="Encounter",
        source_id=f"enc-{idx}",
        text="x" * text_len,
        codes=[],
        metadata={},
    )


def test_shrinker_is_a_noop_under_budget() -> None:
    sources = [_make_source(i, text_len=200) for i in range(2)]
    serialised, report = shrink_background_context(
        sources, [], referring_specialty=None, max_input_tokens=60000
    )

    assert isinstance(report, ShrinkReport)
    assert report.original_source_count == 2
    assert report.kept_source_count == 2
    assert report.dropped_source_ids == []
    assert report.per_source_char_cap == _PROGRESSIVE_CAPS[0]
    assert report.notice is None
    assert "enc-0" in serialised
    assert "enc-1" in serialised


def test_shrinker_picks_smallest_cap_that_fits_before_dropping() -> None:
    sources = [_make_source(i, text_len=8000) for i in range(5)]

    serialised, report = shrink_background_context(
        sources,
        [],
        referring_specialty=None,
        max_input_tokens=4000,
        system_prompt_reserve_tokens=1000,
    )

    assert report.kept_source_count == 5
    assert report.dropped_source_ids == []
    assert report.per_source_char_cap < _PROGRESSIVE_CAPS[0]
    assert report.notice is not None
    assert "shortened" in report.notice
    assert serialised.count('"id": "enc-') == 5


def test_shrinker_drops_sources_when_smallest_cap_still_too_large() -> None:
    sources = [_make_source(i, text_len=20000) for i in range(20)]

    _serialised, report = shrink_background_context(
        sources,
        [],
        referring_specialty=None,
        max_input_tokens=600,
        system_prompt_reserve_tokens=100,
    )

    assert report.kept_source_count >= 1
    assert report.kept_source_count < report.original_source_count
    assert len(report.dropped_source_ids) > 0
    assert report.per_source_char_cap == _PROGRESSIVE_CAPS[-1]
    assert report.notice is not None
    assert "dropped" in report.notice


def test_shrinker_always_keeps_at_least_one_source() -> None:
    sources = [_make_source(i, text_len=100000) for i in range(10)]

    _serialised, report = shrink_background_context(
        sources,
        [],
        referring_specialty=None,
        max_input_tokens=200,
        system_prompt_reserve_tokens=100,
    )

    assert report.kept_source_count == 1


def test_shrinker_handles_empty_sources_gracefully() -> None:
    serialised, report = shrink_background_context(
        [], [], referring_specialty=None, max_input_tokens=60000
    )
    assert report.original_source_count == 0
    assert report.kept_source_count == 0
    assert report.dropped_source_ids == []
    assert report.notice is None
    assert "sources" in serialised


def test_shrinker_notice_is_plain_english() -> None:
    sources = [_make_source(i, text_len=8000) for i in range(5)]
    _serialised, report = shrink_background_context(
        sources,
        [],
        referring_specialty=None,
        max_input_tokens=4000,
        system_prompt_reserve_tokens=1000,
    )

    assert report.notice is not None
    notice = report.notice
    assert "ValidationException" not in notice
    assert "Bedrock" not in notice
    assert "characters" in notice or "records" in notice
    assert notice.endswith(".")


@pytest.mark.parametrize("source_count", [1, 3, 7])
def test_shrinker_is_deterministic(source_count: int) -> None:
    sources = [_make_source(i, text_len=8000) for i in range(source_count)]
    a_serialised, a_report = shrink_background_context(
        sources, [], referring_specialty=None, max_input_tokens=12000
    )
    b_serialised, b_report = shrink_background_context(
        sources, [], referring_specialty=None, max_input_tokens=12000
    )
    assert a_serialised == b_serialised
    assert a_report.kept_source_count == b_report.kept_source_count
    assert a_report.per_source_char_cap == b_report.per_source_char_cap
    assert a_report.dropped_source_ids == b_report.dropped_source_ids
