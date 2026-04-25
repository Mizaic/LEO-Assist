"""Tests for referral-anchored candidate generation."""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_detector_v2.generators.referral_anchored import (
    generate_referral_anchored,
)
from services.analysis_worker.app.episode_detector_v2.types import Signal, TimelineEvent


def _event(encounter_id: str, occurred_on: date) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=occurred_on,
        event_kind="encounter",
    )


def _pathway(encounter_id: str) -> Signal:
    return Signal(
        channel="pathway",
        encounter_id=encounter_id,
        site_key="breast",
        role="referral",
        intent="suspected",
        confidence=0.90,
    )


def test_repeat_referrals_after_quiet_gap_get_separate_windows():
    events = [
        _event("presentation-1", date(2024, 4, 30)),
        _event("referral-1", date(2024, 4, 30)),
        _event("seen-1", date(2024, 5, 5)),
        _event("presentation-2", date(2025, 5, 15)),
        _event("referral-2", date(2025, 5, 15)),
        _event("seen-2", date(2025, 6, 11)),
    ]

    candidates = generate_referral_anchored(
        patient_id="patient",
        events=events,
        signals=[_pathway("referral-1"), _pathway("referral-2")],
    )

    by_anchor = {candidate.anchor_event_id: candidate for candidate in candidates}
    assert "presentation-2" not in by_anchor["referral-1"].encounter_ids
    assert "referral-2" not in by_anchor["referral-1"].encounter_ids
    assert "referral-1" not in by_anchor["referral-2"].encounter_ids
    assert "seen-1" not in by_anchor["referral-2"].encounter_ids
