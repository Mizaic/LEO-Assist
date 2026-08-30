"""Soft guideline word resolver -- three-way outcomes.

Atlas:
  DI-DE8B125E (three-way outcomes)
  DI-0C904503 (optional occurrence window)
  VT-9CEA9081, VT-06FC3ABE
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from libs.guidelines.soft_qualifier import (
    RECENCY_DAYS,
    SoftQualifierError,
    resolve_soft_qualifier,
)


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _qualifier(kind: str, **extra: object) -> dict:
    payload: dict = {"kind": kind}
    payload.update(extra)
    return payload


def test_not_confirmed_when_no_phrase_and_no_count_evidence() -> None:
    """DI-DE8B125E: not_confirmed when there is no phrase and no count evidence."""
    outcome = resolve_soft_qualifier(
        _qualifier("first_presentation"),
        {"letter_text": "vaginal discharge- 10/7 yellowish"},
        NOW,
    )
    assert outcome == "not_confirmed"


def test_confirmed_first_presentation_from_first_episode_phrase() -> None:
    """DI-DE8B125E: confirmed when the letter has first-episode wording."""
    outcome = resolve_soft_qualifier(
        _qualifier("first_presentation"),
        {"letter_text": "This is the first episode of vaginal discharge."},
        NOW,
    )
    assert outcome == "confirmed"


def test_confirmed_first_presentation_from_never_had_this_before() -> None:
    """DI-DE8B125E: confirmed when the letter says never had this before."""
    outcome = resolve_soft_qualifier(
        _qualifier("first_presentation"),
        {"letter_text": "She has never had this before."},
        NOW,
    )
    assert outcome == "confirmed"


def test_confirmed_unexplained_from_phrase() -> None:
    """DI-DE8B125E: confirmed when the letter names unexplained."""
    outcome = resolve_soft_qualifier(
        _qualifier("unexplained"),
        {"letter_text": "unexplained vaginal discharge"},
        NOW,
    )
    assert outcome == "confirmed"


def test_confirmed_unintentional_from_phrase() -> None:
    """DI-DE8B125E: confirmed when the letter names unintentional."""
    outcome = resolve_soft_qualifier(
        _qualifier("unintentional"),
        {"letter_text": "unintentional weight loss of 4kg"},
        NOW,
    )
    assert outcome == "confirmed"


def test_contradicted_when_max_occurrences_exceeded_in_window() -> None:
    """DI-DE8B125E / DI-0C904503: contradicted when max_occurrences is exceeded."""
    dates = [
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 3, 1, tzinfo=timezone.utc),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    ]
    outcome = resolve_soft_qualifier(
        _qualifier(
            "first_presentation",
            concept_id="123",
            max_occurrences=2,
            within_days=365,
        ),
        {"letter_text": "", "concept_occurrences": {"123": dates}},
        NOW,
    )
    assert outcome == "contradicted"


def test_body_site_is_rejected() -> None:
    """DI-DE8B125E: body site is rejected if passed as a soft kind."""
    with pytest.raises(SoftQualifierError, match="body.site|not a soft"):
        resolve_soft_qualifier(_qualifier("body_site"), {"letter_text": ""}, NOW)


def test_unknown_kind_is_rejected() -> None:
    """DI-DE8B125E: only the closed set of kinds is accepted."""
    with pytest.raises(SoftQualifierError):
        resolve_soft_qualifier(_qualifier("cervical_site"), {"letter_text": ""}, NOW)


def test_occurrence_window_uses_lab_recency_days() -> None:
    """DI-0C904503: a concept chip may use the lab recency day set."""
    assert RECENCY_DAYS == frozenset({30, 90, 180, 365, 730, 1825})
    with pytest.raises(SoftQualifierError, match="within_days"):
        resolve_soft_qualifier(
            _qualifier(
                "first_presentation",
                concept_id="123",
                max_occurrences=1,
                within_days=14,
            ),
            {"letter_text": "", "concept_occurrences": {"123": []}},
            NOW,
        )


def test_missing_history_is_not_confirmed_on_soft_count_window() -> None:
    """DI-0C904503: missing history is not_confirmed, never a fail here."""
    outcome = resolve_soft_qualifier(
        _qualifier(
            "first_presentation",
            concept_id="123",
            max_occurrences=1,
            within_days=365,
        ),
        {"letter_text": "", "concept_occurrences": {}},
        NOW,
    )
    assert outcome == "not_confirmed"


def test_min_occurrences_confirmed_when_count_met() -> None:
    """DI-0C904503: min_occurrences met confirms persistent / repeat."""
    dates = [
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 1, tzinfo=timezone.utc),
    ]
    outcome = resolve_soft_qualifier(
        _qualifier(
            "persistent",
            concept_id="123",
            min_occurrences=2,
            within_days=365,
        ),
        {"letter_text": "", "concept_occurrences": {"123": dates}},
        NOW,
    )
    assert outcome == "confirmed"
