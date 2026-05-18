"""Tests for `services/analysis_worker/app/episode_engine/writer_rollups.py`.

Atlas trace:
  DO: DO-F2E2A70B
  DI: DI-5B694FBE

Rollups feed the NCDA Avoidable Delays dashboard tile. They MUST be
deterministic in/out -- no graph access, no LLM, no clock.
"""

from __future__ import annotations

import json
from datetime import date

from services.analysis_worker.app.episode_engine.schemas import (
    Disruption,
    Milestone,
    SafetyNetting,
)
from services.analysis_worker.app.episode_engine.writer_rollups import (
    disruption_phase,
    disruption_summary,
    earliest_milestone_date,
    earliest_phase,
    first_presentation,
    first_seen_date,
    outcome_letter_date,
    safety_netting_payload,
)


def _ms(t: str, d: str, *, place: str | None = None) -> Milestone:
    return Milestone(
        type=t,
        date=date.fromisoformat(d),
        encounter_id="E1",
        evidence_quote="quote here",
        confidence=0.9,
        reasoning="r",
        presentation_place=place,
    )


def _disruption(d: str, category: str) -> Disruption:
    return Disruption(
        date=date.fromisoformat(d),
        category=category,
        description="something happened",
        encounter_id="E1",
        evidence_quote="quote here",
        confidence=0.8,
    )


class TestMilestoneDatePickers:
    def test_first_seen_returns_iso_date(self):
        ms = [_ms("first_seen", "2025-03-01")]
        assert first_seen_date(ms) == "2025-03-01"

    def test_first_seen_returns_none_when_absent(self):
        assert first_seen_date([_ms("referral", "2025-01-01")]) is None

    def test_first_presentation_picks_earliest(self):
        ms = [
            _ms("first_presentation", "2025-02-15", place="gp_surgery"),
            _ms("first_presentation", "2025-01-01", place="hospital_outpatient"),
        ]
        d, place = first_presentation(ms)
        assert d == "2025-01-01"
        assert place == "hospital_outpatient"

    def test_first_presentation_returns_none_pair_when_absent(self):
        assert first_presentation([]) == (None, None)

    def test_outcome_letter_picks_earliest(self):
        ms = [
            _ms("outcome_letter", "2025-04-10"),
            _ms("outcome_letter", "2025-03-01"),
        ]
        assert outcome_letter_date(ms) == "2025-03-01"

    def test_earliest_milestone_date_filters_by_type(self):
        ms = [
            _ms("referral", "2025-02-01"),
            _ms("referral", "2025-01-01"),
            _ms("first_seen", "2024-12-01"),
        ]
        assert earliest_milestone_date(ms, "referral") == "2025-01-01"
        assert earliest_milestone_date(ms, "diagnosis_confirmed") is None


class TestDisruptionPhase:
    def test_before_first_presentation(self):
        out = disruption_phase(
            date(2025, 1, 1),
            first_presentation_iso="2025-02-01",
            referral_iso="2025-03-01",
        )
        assert out == "before_presentation"

    def test_between_presentation_and_referral(self):
        out = disruption_phase(
            date(2025, 2, 15),
            first_presentation_iso="2025-02-01",
            referral_iso="2025-03-01",
        )
        assert out == "pres_to_referral"

    def test_on_or_after_referral(self):
        assert disruption_phase(
            date(2025, 3, 1),
            first_presentation_iso="2025-02-01",
            referral_iso="2025-03-01",
        ) == "after_referral"

    def test_default_after_referral_when_no_first_presentation(self):
        assert disruption_phase(
            date(2025, 1, 1),
            first_presentation_iso=None,
            referral_iso=None,
        ) == "after_referral"

    def test_invalid_iso_treated_as_missing(self):
        assert disruption_phase(
            date(2025, 1, 1),
            first_presentation_iso="not-a-date",
            referral_iso=None,
        ) == "after_referral"


class TestEarliestPhase:
    def test_returns_none_for_empty(self):
        assert earliest_phase([]) is None

    def test_picks_earliest_phase_in_order(self):
        assert earliest_phase(["after_referral", "before_presentation"]) == (
            "before_presentation"
        )
        assert earliest_phase(["after_referral", "pres_to_referral"]) == (
            "pres_to_referral"
        )
        assert earliest_phase(["after_referral"]) == "after_referral"


class TestSafetyNettingPayload:
    def test_none_payload_is_recorded_false(self):
        out = safety_netting_payload(None)
        assert out["safety_netting_recorded"] is False
        assert out["safety_netting_evidence"] is None
        assert out["safety_netting_confidence"] == 0.0

    def test_unrecorded_payload_is_recorded_false(self):
        sn = SafetyNetting(recorded=False)
        out = safety_netting_payload(sn)
        assert out["safety_netting_recorded"] is False

    def test_recorded_payload_flattens_fields(self):
        sn = SafetyNetting(
            recorded=True,
            evidence_quote="advised to return if symptoms worsen",
            encounter_id="E9",
            date=date(2025, 5, 1),
            confidence=0.7,
        )
        out = safety_netting_payload(sn)
        assert out["safety_netting_recorded"] is True
        assert out["safety_netting_encounter_id"] == "E9"
        assert out["safety_netting_date"] == "2025-05-01"
        assert out["safety_netting_confidence"] == 0.7


class TestDisruptionSummary:
    def test_empty_list_marks_no_delay(self):
        out = disruption_summary(
            [], first_presentation_iso=None, referral_iso=None
        )
        assert out["disruption_count"] == 0
        assert out["avoidable_delay"] is False
        assert out["avoidable_delay_phase"] is None
        assert out["per_disruption"] == []
        assert out["has_referral_disruption"] is False

    def test_referral_category_sets_referral_flag(self):
        d = _disruption("2025-02-01", "referral_lost_or_not_received")
        out = disruption_summary(
            [d],
            first_presentation_iso="2025-01-01",
            referral_iso="2025-03-01",
        )
        assert out["has_referral_disruption"] is True
        assert out["disruption_count"] == 1

    def test_summary_picks_earliest_phase_across_disruptions(self):
        ds = [
            _disruption("2025-04-01", "appointment_dna"),
            _disruption("2025-01-01", "appointment_dna"),
        ]
        out = disruption_summary(
            ds,
            first_presentation_iso="2025-02-01",
            referral_iso="2025-03-01",
        )
        assert out["avoidable_delay_phase"] == "before_presentation"

    def test_categories_sorted_and_deduped(self):
        ds = [
            _disruption("2025-04-01", "appointment_dna"),
            _disruption("2025-04-02", "appointment_dna"),
            _disruption("2025-04-03", "letter_received_late"),
        ]
        out = disruption_summary(
            ds,
            first_presentation_iso="2025-01-01",
            referral_iso="2025-03-01",
        )
        assert out["disruption_categories"] == [
            "appointment_dna",
            "letter_received_late",
        ]

    def test_disruptions_json_round_trips(self):
        d = _disruption("2025-04-01", "appointment_dna")
        out = disruption_summary(
            [d],
            first_presentation_iso="2025-01-01",
            referral_iso="2025-03-01",
        )
        rows = json.loads(out["disruptions_json"])
        assert rows[0]["category"] == "appointment_dna"
        assert rows[0]["phase"] == "after_referral"
        assert rows[0]["date"] == "2025-04-01"
