"""Tests for `scripts/build_ncda_export.py`.

Atlas trace:
  - Episode KPI persistence verification (VT-342D6854)
  - NCDA ground-truth regression harness (VT-84DAE8A0)
  Both VTs share DO/DI = the build_ncda_export module.

Tests focus on the deterministic helpers used to build each row of the
NCDA export. Anything touching Neo4j / pickle / dotenv lives in
`build_export()` and is left for an integration test.
"""

from __future__ import annotations

from datetime import date

from scripts.build_ncda_export import (
    _classify_presentation,
    _diagnosis_label,
    _empty_stage_fields,
    _gap_days,
    _index_by_patient,
    _is_clinical,
    _referral_label,
    _to_date,
    _window,
    compute_intervals,
)


class TestToDate:
    def test_parses_iso_date_string(self):
        assert _to_date("2025-04-21") == date(2025, 4, 21)

    def test_parses_iso_datetime_truncating_time(self):
        assert _to_date("2025-04-21T14:30:00") == date(2025, 4, 21)

    def test_returns_none_for_empty_or_garbage(self):
        assert _to_date("") is None
        assert _to_date(None) is None
        assert _to_date("not-a-date") is None


class TestIndexByPatient:
    def test_groups_and_sorts_by_date(self):
        encs = [
            {"pid": "P1", "date": "2025-02-01", "text": "later"},
            {"pid": "P1", "date": "2025-01-01", "text": "earlier"},
            {"pid": "P2", "date": "2025-03-01", "text": "other"},
        ]
        out = _index_by_patient(encs)
        assert list(out.keys()) == ["P1", "P2"]
        assert [e["text"] for e in out["P1"]] == ["earlier", "later"]

    def test_drops_rows_missing_date_or_text(self):
        encs = [
            {"pid": "P1", "date": "", "text": "skip"},
            {"pid": "P1", "date": "2025-01-01", "text": ""},
            {"pid": "P1", "date": "2025-02-01", "text": "keep"},
        ]
        out = _index_by_patient(encs)
        assert len(out["P1"]) == 1
        assert out["P1"][0]["text"] == "keep"


class TestWindow:
    def _enc(self, d):
        return {"date": d, "text": "x"}

    def test_inclusive_on_both_sides(self):
        encs = [self._enc(d) for d in
                ("2025-01-01", "2025-01-15", "2025-02-01", "2025-03-01")]
        out = _window(encs, date(2025, 1, 15), date(2025, 2, 1))
        dates = [e["date"] for e in out]
        assert dates == ["2025-01-15", "2025-02-01"]

    def test_unbounded_start(self):
        encs = [self._enc("2024-01-01"), self._enc("2025-01-01")]
        out = _window(encs, None, date(2024, 12, 31))
        assert [e["date"] for e in out] == ["2024-01-01"]

    def test_unbounded_end(self):
        encs = [self._enc("2024-01-01"), self._enc("2025-01-01")]
        out = _window(encs, date(2024, 6, 1), None)
        assert [e["date"] for e in out] == ["2025-01-01"]

    def test_skips_unparseable_dates(self):
        encs = [self._enc("not-a-date"), self._enc("2025-01-01")]
        out = _window(encs, None, None)
        assert len(out) == 1


class TestIsClinical:
    def test_empty_text_is_not_clinical(self):
        assert _is_clinical("") is False

    def test_text_with_clinical_first_line_is_clinical(self):
        assert _is_clinical("Reviewed in clinic today") is True


class TestGapDays:
    def test_returns_none_when_either_side_missing(self):
        assert _gap_days(None, "2025-01-01") is None
        assert _gap_days("2025-01-01", None) is None

    def test_returns_inclusive_day_count(self):
        diff = _gap_days("2025-01-01", "2025-01-11")
        assert diff is not None
        assert diff >= 10


class TestComputeIntervals:
    def test_returns_all_four_keys(self):
        intervals = compute_intervals(
            {
                "first_presentation": "2025-01-01",
                "referral": "2025-01-15",
                "first_seen": "2025-02-01",
                "diagnosis_date": "2025-03-01",
            }
        )
        assert set(intervals.keys()) == {
            "days_presentation_to_referral",
            "days_referral_to_first_seen",
            "days_presentation_to_diagnosis",
            "days_referral_to_diagnosis",
        }
        assert all(v is not None for v in intervals.values())

    def test_returns_none_for_missing_fields(self):
        intervals = compute_intervals({"first_presentation": "2025-01-01"})
        assert intervals["days_presentation_to_referral"] is None


class TestEmptyStageFields:
    def test_canonical_unset_shape(self):
        out = _empty_stage_fields()
        assert out["stage_at_diagnosis"] is None
        assert out["stage_early_late"] == "unknown"
        assert out["stage_system"] == "unknown"
        assert out["stage_evidence"] == ""
        assert out["stage_confidence"] == 0.0


class TestPresentationClassification:
    def test_known_referral_types(self):
        assert _classify_presentation("ae_initiated") == "A&E / Emergency Department"
        assert _classify_presentation("gp_initiated") == "GP Surgery"
        assert _classify_presentation("specialist_initiated") == (
            "Other primary care facility"
        )
        assert _classify_presentation("screening_initiated") == (
            "Other - Screening programme"
        )

    def test_default_falls_back_to_gp(self):
        assert _classify_presentation(None) == "GP Surgery"
        assert _classify_presentation("anything-else") == "GP Surgery"


class TestReferralLabel:
    def test_known_referral_labels(self):
        assert _referral_label("ae_initiated").startswith("Emergency referral")
        assert _referral_label("gp_initiated") == "Urgent / TWW for suspected cancer"
        assert _referral_label("specialist_initiated") == "Routine / Non-urgent"
        assert _referral_label("screening_initiated") == "Screening detected"

    def test_default_is_two_week_wait(self):
        assert _referral_label(None) == "Urgent / TWW for suspected cancer"


class TestDiagnosisLabel:
    def test_cancer_outcome_uses_site_map(self):
        assert _diagnosis_label(
            {"diagnosis_outcome": "cancer", "cancer_type": "breast"}
        ) == "Breast"
        assert _diagnosis_label(
            {"diagnosis_outcome": "cancer", "cancer_type": "lower_gi"}
        ) == "Colorectal"

    def test_unknown_cancer_type_falls_back_to_other(self):
        assert _diagnosis_label(
            {"diagnosis_outcome": "cancer", "cancer_type": "exotic"}
        ) == "Other"

    def test_benign_outcome_returns_non_cancer_label(self):
        assert _diagnosis_label({"diagnosis_outcome": "benign"}) == (
            "Non-cancer diagnosis (benign)"
        )

    def test_missing_outcome_returns_unknown_label(self):
        assert _diagnosis_label({}) == "Unknown / pathway incomplete"
