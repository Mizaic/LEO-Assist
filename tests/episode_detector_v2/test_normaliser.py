"""Tests for episode_detector_v2.normaliser.

Atlas trace:
  DI: DI-8A5FCF4F
  VT: (created in Phase 1 once tests are recorded)
"""

from __future__ import annotations

from datetime import date, datetime

from services.analysis_worker.app.episode_detector_v2.normaliser import (
    normalise_from_rows,
    _to_date,
    _row_to_event,
)


def _row(**overrides):
    base = {
        "encounter_id": "enc-1",
        "occurred_on": "2024-03-15",
        "encounter_type": "primary_care",
        "doc_snippets": ["Patient seen with breast lump."],
        "codes": [{"concept_id": "395557000", "display_name": "Breast lump"}],
        "observations": [],
        "referral": None,
    }
    base.update(overrides)
    return base


def test_to_date_handles_iso_string_datetime_and_date():
    assert _to_date("2024-03-15") == date(2024, 3, 15)
    assert _to_date(datetime(2024, 3, 15, 9, 30)) == date(2024, 3, 15)
    assert _to_date(date(2024, 3, 15)) == date(2024, 3, 15)


def test_to_date_returns_none_for_blank_or_garbage():
    assert _to_date(None) is None
    assert _to_date("") is None
    assert _to_date("not-a-date") is None


def test_row_with_missing_encounter_id_is_dropped():
    assert _row_to_event(_row(encounter_id="")) is None


def test_row_with_missing_date_is_dropped():
    assert _row_to_event(_row(occurred_on=None)) is None


def test_normalise_orders_events_by_date_then_id():
    rows = [
        _row(encounter_id="b", occurred_on="2024-03-15"),
        _row(encounter_id="a", occurred_on="2024-03-15"),
        _row(encounter_id="c", occurred_on="2024-01-01"),
    ]
    events = normalise_from_rows(rows)
    assert [e.encounter_id for e in events] == ["c", "a", "b"]


def test_normalise_drops_codes_without_concept_id():
    rows = [
        _row(
            codes=[
                {"concept_id": "", "display_name": "noise"},
                {"concept_id": "395557000", "display_name": "Breast lump"},
            ]
        )
    ]
    events = normalise_from_rows(rows)
    assert len(events) == 1
    assert len(events[0].coded_entities) == 1
    assert events[0].coded_entities[0]["concept_id"] == "395557000"


def test_normalise_truncates_text_snippet_at_4000_chars():
    long = "x" * 6000
    rows = [_row(doc_snippets=[long])]
    events = normalise_from_rows(rows)
    assert len(events[0].text_snippet) == 4000


def test_normalise_is_pure_and_deterministic():
    rows = [_row(encounter_id="a"), _row(encounter_id="b")]
    a = normalise_from_rows(rows)
    b = normalise_from_rows(rows)
    assert [e.encounter_id for e in a] == [e.encounter_id for e in b]
