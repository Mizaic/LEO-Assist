"""Unit tests for libs/metrics/intervals.py.

Covers the pure-math core shared by the runtime KPI calculator and the
NCDA ground-truth export. See DI-LEO-AI-125, DO-LEO-AI-125,
VT-LEO-AI-120.
"""

from __future__ import annotations

from datetime import date

import pytest

from libs.metrics import (
    INTERVAL_METRIC_NAMES,
    compute_interval_kpis,
    days_between,
    pick_earliest_milestone,
)


class TestDaysBetween:
    def test_basic_gap(self):
        assert days_between("2024-01-01", "2024-01-15") == 14

    def test_negative_gap(self):
        assert days_between("2024-01-15", "2024-01-01") == -14

    def test_same_day(self):
        assert days_between("2024-06-15", "2024-06-15") == 0

    def test_accepts_date_objects(self):
        d1 = date(2024, 1, 1)
        d2 = date(2024, 2, 1)
        assert days_between(d1, d2) == 31

    def test_truncates_datetime_strings(self):
        assert days_between("2024-01-01T09:00:00", "2024-01-08T18:30:00") == 7

    def test_returns_none_for_missing(self):
        assert days_between(None, "2024-01-01") is None
        assert days_between("2024-01-01", None) is None
        assert days_between("", "2024-01-01") is None

    def test_returns_none_for_unparseable(self):
        assert days_between("not-a-date", "2024-01-01") is None
        assert days_between("2024-01-01", "nope") is None


class TestPickEarliestMilestone:
    def test_picks_earliest_non_empty(self):
        ms = {
            "diagnosis": "2024-02-10",
            "diagnosis_confirmed": "2024-02-01",
        }
        assert pick_earliest_milestone(ms, ("diagnosis_confirmed", "diagnosis")) == "2024-02-01"

    def test_ignores_missing_keys(self):
        ms = {"diagnosis": "2024-02-10"}
        assert pick_earliest_milestone(ms, ("diagnosis_confirmed", "diagnosis")) == "2024-02-10"

    def test_returns_none_when_all_missing(self):
        ms = {"unrelated": "2024-02-01"}
        assert pick_earliest_milestone(ms, ("diagnosis_confirmed", "diagnosis")) is None

    def test_drops_unparseable(self):
        ms = {"diagnosis": "bogus", "diagnosis_confirmed": "2024-02-01"}
        assert pick_earliest_milestone(ms, ("diagnosis_confirmed", "diagnosis")) == "2024-02-01"


class TestComputeIntervalKPIs:
    def test_full_pathway(self):
        ms = {
            "first_presentation": "2024-01-01",
            "referral": "2024-01-15",
            "diagnosis": "2024-02-01",
            "treatment": "2024-03-01",
        }
        out = compute_interval_kpis(ms)
        assert out == {
            "days_presentation_to_referral": 14,
            "days_referral_to_diagnosis": 17,
            "days_diagnosis_to_treatment": 29,
        }

    def test_runtime_milestone_keys(self):
        ms = {
            "first_presentation": "2024-01-01",
            "referral": "2024-01-15",
            "diagnosis_confirmed": "2024-02-01",
            "treatment_started": "2024-03-01",
        }
        out = compute_interval_kpis(ms)
        assert out["days_referral_to_diagnosis"] == 17
        assert out["days_diagnosis_to_treatment"] == 29

    def test_ground_truth_keys(self):
        # Ground-truth export uses diagnosis_date, referral_date etc.
        ms = {
            "presentation_date": "2024-01-01",
            "referral_date": "2024-01-15",
            "diagnosis_date": "2024-02-01",
        }
        out = compute_interval_kpis(ms)
        assert out == {
            "days_presentation_to_referral": 14,
            "days_referral_to_diagnosis": 17,
        }

    def test_partial_pathway_only_emits_valid(self):
        ms = {"referral": "2024-01-15", "diagnosis": "2024-02-01"}
        out = compute_interval_kpis(ms)
        assert out == {"days_referral_to_diagnosis": 17}

    def test_empty_milestones(self):
        assert compute_interval_kpis({}) == {}

    def test_unparseable_skipped(self):
        ms = {"first_presentation": "2024-01-01", "referral": "bogus"}
        assert compute_interval_kpis(ms) == {}


class TestIntervalMetricNames:
    def test_canonical_set(self):
        assert INTERVAL_METRIC_NAMES == (
            "days_presentation_to_referral",
            "days_referral_to_diagnosis",
            "days_diagnosis_to_treatment",
        )


class TestParity:
    """Runtime and ground-truth callers must produce identical numbers."""

    def test_runtime_vs_ground_truth_keys_equivalent(self):
        runtime = {
            "first_presentation": "2024-01-01",
            "referral": "2024-01-15",
            "diagnosis_confirmed": "2024-02-01",
        }
        ground_truth = {
            "presentation_date": "2024-01-01",
            "referral_date": "2024-01-15",
            "diagnosis_date": "2024-02-01",
        }
        assert compute_interval_kpis(runtime) == compute_interval_kpis(ground_truth)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
