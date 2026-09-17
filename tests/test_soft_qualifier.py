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


def test_first_presentation_is_open_when_no_repeat_and_no_older_code() -> None:
    """DI-DE8B125E: first time when the letter is not a repeat and history is new."""
    outcome = resolve_soft_qualifier(
        _qualifier("first_presentation", concept_id="271939006", within_days=90),
        {
            "letter_text": "vaginal discharge- 10/7 yellowish",
            "concept_occurrences": {"271939006": []},
        },
        NOW,
    )
    assert outcome == "confirmed"


def test_first_presentation_contradicted_by_chronic_or_repeat_phrase() -> None:
    """DI-DE8B125E: not first time when the letter names a chronic or repeat problem."""
    outcome = resolve_soft_qualifier(
        _qualifier("first_presentation", concept_id="271939006", within_days=90),
        {"letter_text": "chronic recurrent vaginal discharge"},
        NOW,
    )
    assert outcome == "contradicted"


def test_medication_repeats_heading_does_not_contradict_first_presentation() -> None:
    """Form chrome 'Repeats' is not a repeat presentation of discharge."""
    outcome = resolve_soft_qualifier(
        _qualifier(
            "first_presentation",
            concept_id="271939006",
            within_days=90,
            term="Vaginal discharge (finding)",
        ),
        {"letter_text": "vaginal discharge- yellowish\n2. Repeats | None |"},
        NOW,
    )
    assert outcome == "confirmed"


def test_pathway_recurrent_bleeding_does_not_contradict_discharge() -> None:
    """PMB pathway advice about recurrent bleeding is not recurrent discharge."""
    outcome = resolve_soft_qualifier(
        _qualifier(
            "first_presentation",
            concept_id="271939006",
            within_days=90,
            term="Vaginal discharge (finding)",
        ),
        {
            "letter_text": (
                "yellow vaginal discharge. advise patient to return if "
                "persistent or recurrent bleeding. Consider giving "
                "patient information sheet"
            ),
        },
        NOW,
    )
    assert outcome == "confirmed"


def test_first_presentation_contradicted_by_same_code_older_than_three_months() -> None:
    """DI-DE8B125E: not first time when the same code is older than 90 days."""
    outcome = resolve_soft_qualifier(
        _qualifier("first_presentation", concept_id="271939006", within_days=90),
        {
            "letter_text": "vaginal discharge",
            "concept_occurrences": {
                "271939006": [datetime(2026, 1, 1, tzinfo=timezone.utc)]
            },
        },
        NOW,
    )
    assert outcome == "contradicted"


def test_not_confirmed_when_no_phrase_and_no_count_evidence() -> None:
    """DI-DE8B125E: unexplained stays not_confirmed when there is no phrase."""
    outcome = resolve_soft_qualifier(
        _qualifier("unexplained"),
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


def test_missing_history_is_open_for_first_presentation() -> None:
    """DI-0C904503: missing history is first time, not a block."""
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
    assert outcome == "confirmed"


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


def test_historical_concept_contradicts_unexplained() -> None:
    outcome = resolve_soft_qualifier(
        _qualifier("unexplained", concept_id="66308002"),
        {
            "letter_text": "unexplained fracture",
            "historical_concept_ids": ["66308002"],
        },
        NOW,
    )
    assert outcome == "contradicted"


def test_hard_unexplained_not_confirmed_blocks_leaf() -> None:
    from libs.guidelines.soft_qualifier import apply_soft_qualifiers

    unverified: list[str] = []
    allowed = apply_soft_qualifiers(
        {
            "criterion": {
                "snomed_concept_id": "66308002",
                "soft_qualifiers": [{"kind": "unexplained", "enforcement": "hard"}],
            }
        },
        {"letter_text": "past fracture of humerus"},
        NOW,
        unverified,
    )
    assert allowed is False
