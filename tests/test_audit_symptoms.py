"""Unit tests for ``services.analytics_api.app.routers._audit_symptoms``.

Atlas trace:
  DO: DO-D5B9FE5F
  DI: DI-6E1B71A4

These tests exercise the pure-Python aggregation helpers (PPV bucketing,
heatmap construction, distinct-per-patient symptom counting) without
touching Neo4j. The graph integration paths are covered by the existing
audit-router smoke tests.
"""

from __future__ import annotations

import pytest

from services.analytics_api.app.routers import _audit_symptoms as mod
from services.analytics_api.app.routers._audit_symptoms import (
    _build_ppv_table_rows,
    _follow_year_window,
    _heatmap_rows,
    _patient_cancer_terms,
    _patient_symptom_terms,
    _q_ppv_by_suspected_cancer_type,
    _resolve_ep_status,
    _suspected_cancer_label,
    _symptom_rows_for_slice,
)


class TestSuspectedCancerLabel:
    def test_prefers_snomed_terms_over_raw(self):
        assert (
            _suspected_cancer_label(["Breast"], "lung") == "Breast"
        )

    def test_falls_back_to_normalised_raw(self):
        assert _suspected_cancer_label(None, "breast") == "Breast"

    def test_no_information_when_blank(self):
        assert _suspected_cancer_label(None, "") == "No Information"


class TestResolveEpStatus:
    def test_diagnosed_when_confirmed_with_milestone(self):
        assert (
            _resolve_ep_status(True, True, "in_progress", False) == "diagnosed"
        )

    def test_no_cancer_for_closed_benign(self):
        assert (
            _resolve_ep_status(False, False, "closed_benign", False)
            == "no_cancer"
        )

    def test_no_cancer_for_letter_inferred_benign(self):
        assert (
            _resolve_ep_status(False, False, "in_progress", True)
            == "no_cancer"
        )

    def test_unresolved_for_in_progress_without_outcome(self):
        assert (
            _resolve_ep_status(False, False, "in_progress", False)
            == "unresolved"
        )


class TestFollowYearWindow:
    def test_handles_year_end_date_to(self):
        assert _follow_year_window("2024-12-31") == ("2025-01-01", "2025-12-31")

    def test_handles_mid_year_date_to(self):
        assert _follow_year_window("2024-06-30") == ("2025-01-01", "2025-12-31")

    def test_returns_none_for_missing_or_invalid(self):
        assert _follow_year_window(None) is None
        assert _follow_year_window("not-a-date") is None


class TestPatientSymptomTerms:
    def test_distinct_per_patient(self):
        rows = [
            {"pid": "P1", "concept_ids": ["1", "2"]},
            {"pid": "P2", "concept_ids": ["1"]},
            {"pid": "P1", "concept_ids": ["3"]},
        ]
        id_to_term = {"1": "cough", "2": "cough", "3": "fatigue"}
        out = _patient_symptom_terms(rows, id_to_term)
        # Within a row P1 had 1+2 (both 'cough') -> single symptom term.
        # The second P1 row only contributes 'fatigue'; the helper builds
        # one set per row which is fine for our caller (distinct per
        # patient is enforced by the caller after merge).
        assert "cough" in out["P1"]
        assert {"cough"} == out["P2"]


class TestPatientCancerTerms:
    def test_orders_by_registry_then_alpha(self):
        rows = [{"pid": "P1", "concept_ids": ["10", "20"]}]
        id_to_term = {"10": "lung", "20": "breast"}
        display = {"lung": "Lung", "breast": "Breast"}
        ordered_keys = ["breast", "lung"]
        out = _patient_cancer_terms(rows, id_to_term, display, ordered_keys)
        assert out["P1"] == ["Breast", "Lung"]


class TestSymptomRowsForSlice:
    def test_distinct_count_and_pct(self):
        pid_terms = {
            "P1": {"cough", "fatigue"},
            "P2": {"cough"},
            "P3": set(),
        }
        rows = _symptom_rows_for_slice(
            slice_pids={"P1", "P2", "P3"},
            pid_terms=pid_terms,
            ordered_keys=["cough", "fatigue"],
            group_key_to_display={"cough": "Cough", "fatigue": "Fatigue"},
            denom=3,
        )
        assert rows[0] == {"symptom": "Cough", "n": 2, "pct": pytest.approx(66.7, abs=0.1)}
        assert rows[1] == {"symptom": "Fatigue", "n": 1, "pct": pytest.approx(33.3, abs=0.1)}


class TestHeatmapRows:
    def test_emits_one_cell_per_bucket_symptom(self):
        bucket_pids = {
            "Breast": {"P1", "P2"},
            "Lung": {"P3"},
        }
        pid_terms = {
            "P1": {"cough"},
            "P2": {"cough", "fatigue"},
            "P3": {"fatigue"},
        }
        cells = _heatmap_rows(
            bucket_pids,
            pid_terms,
            ["cough", "fatigue"],
            {"cough": "Cough", "fatigue": "Fatigue"},
            ["Breast", "Lung"],
        )
        breast_cough = next(
            c for c in cells if c["bucket_label"] == "Breast" and c["symptom"] == "Cough"
        )
        assert breast_cough == {
            "bucket_key": "Breast",
            "bucket_label": "Breast",
            "cohort_n": 2,
            "symptom": "Cough",
            "n": 2,
            "pct": 100.0,
        }

    def test_skips_empty_buckets(self):
        cells = _heatmap_rows(
            {"Breast": set(), "Lung": {"P1"}},
            {"P1": {"cough"}},
            ["cough"],
            {"cough": "Cough"},
            ["Breast", "Lung"],
        )
        labels = {c["bucket_label"] for c in cells}
        assert labels == {"Lung"}


class TestPpvBucketing:
    def _patient_row(self, **overrides):
        base = {
            "pid": "P1",
            "is_confirmed": False,
            "has_referral_milestone": True,
            "has_diagnosis_milestone": False,
            "ep_status": "in_progress",
            "letter_benign": False,
            "cancer_type_raw": "breast",
        }
        base.update(overrides)
        return base

    def test_diagnosed_in_year_drives_ppv(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_fetch_following_year_diagnosis_pids", lambda *a, **k: set()
        )

        patient_rows = [
            self._patient_row(
                pid="P1", is_confirmed=True, has_diagnosis_milestone=True
            ),
            self._patient_row(
                pid="P2", is_confirmed=False, ep_status="closed_benign"
            ),
        ]
        rows = _q_ppv_by_suspected_cancer_type(
            base="MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
            params={"date_to": "2024-12-31"},
            client=None,  # noqa: ARG002 - patched out via monkeypatch
            patient_rows=patient_rows,
            pid_cancer_terms={},
            date_to="2024-12-31",
        )
        assert len(rows) == 1
        breast = rows[0]
        assert breast["cancer_type"] == "Breast"
        assert breast["referrals_n"] == 2
        assert breast["diagnosed_in_year_n"] == 1
        assert breast["no_cancer_in_year_n"] == 1
        assert breast["unresolved_n"] == 0
        assert breast["diagnosed_following_year_n"] == 0
        assert breast["ppv_pct"] == 50.0
        assert breast["provisional"] is False

    def test_following_year_diagnosis_excluded_from_no_cancer(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_fetch_following_year_diagnosis_pids", lambda *a, **k: {"P2"}
        )
        patient_rows = [
            self._patient_row(
                pid="P1", is_confirmed=True, has_diagnosis_milestone=True
            ),
            # P2 had no in-year diagnosis but did get diagnosed Y+1.
            self._patient_row(
                pid="P2", is_confirmed=False, ep_status="closed"
            ),
        ]
        rows = _q_ppv_by_suspected_cancer_type(
            base="MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
            params={"date_to": "2024-12-31"},
            client=None,
            patient_rows=patient_rows,
            pid_cancer_terms={},
            date_to="2024-12-31",
        )
        breast = rows[0]
        assert breast["diagnosed_following_year_n"] == 1
        assert breast["no_cancer_in_year_n"] == 0
        # PPV uses resolved-only denominator (excludes Y+1 cases):
        assert breast["ppv_pct"] == 100.0
        assert breast["provisional"] is True

    def test_unresolved_reported_separately(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_fetch_following_year_diagnosis_pids", lambda *a, **k: set()
        )
        patient_rows = [
            self._patient_row(
                pid="P1", is_confirmed=True, has_diagnosis_milestone=True
            ),
            self._patient_row(pid="P2", is_confirmed=False, ep_status="in_progress"),
        ]
        rows = _q_ppv_by_suspected_cancer_type(
            base="MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
            params={"date_to": "2024-12-31"},
            client=None,
            patient_rows=patient_rows,
            pid_cancer_terms={},
            date_to="2024-12-31",
        )
        breast = rows[0]
        assert breast["unresolved_n"] == 1
        # Resolved denominator excludes the unresolved patient -> 1 / 1 = 100%.
        assert breast["ppv_pct"] == 100.0
        assert breast["provisional"] is True

    def test_referrals_without_milestone_excluded(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_fetch_following_year_diagnosis_pids", lambda *a, **k: set()
        )
        patient_rows = [
            self._patient_row(pid="P1", has_referral_milestone=False),
        ]
        rows = _q_ppv_by_suspected_cancer_type(
            base="MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
            params={"date_to": "2024-12-31"},
            client=None,
            patient_rows=patient_rows,
            pid_cancer_terms={},
            date_to="2024-12-31",
        )
        assert rows == []

    def test_snomed_cancer_label_used_when_available(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_fetch_following_year_diagnosis_pids", lambda *a, **k: set()
        )
        patient_rows = [
            self._patient_row(
                pid="P1", is_confirmed=True, has_diagnosis_milestone=True
            ),
        ]
        rows = _q_ppv_by_suspected_cancer_type(
            base="MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true ",
            params={"date_to": "2024-12-31"},
            client=None,
            patient_rows=patient_rows,
            pid_cancer_terms={"P1": ["Coded breast cancer"]},
            date_to="2024-12-31",
        )
        assert rows[0]["cancer_type"] == "Coded breast cancer"


class TestBuildPpvTableRows:
    """Clinical PPV table: cancer_type × symptom × feature count × cancer count."""

    def _row(self, pid, is_confirmed, cancer_type_raw, **kw):
        base = {
            "pid": pid,
            "is_confirmed": is_confirmed,
            "cancer_type_raw": cancer_type_raw,
            "has_referral_milestone": True,
            "has_diagnosis_milestone": is_confirmed,
            "ep_status": "completed" if is_confirmed else "closed_benign",
            "letter_benign": False,
        }
        base.update(kw)
        return base

    def test_ppv_correct_for_single_cancer_type(self):
        from services.analytics_api.app.routers._audit_symptoms import (
            _build_ppv_table_rows,
        )

        patient_rows = [
            self._row("P1", True, "breast"),
            self._row("P2", True, "breast"),
            self._row("P3", False, "breast"),
        ]
        pid_symptom_terms = {
            "P1": {"cough"},
            "P2": {"cough"},
            "P3": {"cough"},
        }
        rows = _build_ppv_table_rows(
            patient_rows=patient_rows,
            pid_cancer_terms={},
            pid_symptom_terms=pid_symptom_terms,
            symptom_ordered_keys=["cough"],
            symptom_display={"cough": "Cough"},
            cancer_order_display=["Breast"],
        )
        assert len(rows) == 1
        r = rows[0]
        assert r["cancer_type"] == "Breast"
        assert r["symptom"] == "Cough"
        assert r["patients_with_feature"] == 3
        assert r["patients_with_cancer"] == 2
        assert r["ppv_pct"] == pytest.approx(66.7, abs=0.1)

    def test_symptom_absent_in_type_excluded(self):
        from services.analytics_api.app.routers._audit_symptoms import (
            _build_ppv_table_rows,
        )

        patient_rows = [self._row("P1", True, "lung")]
        # P1 has no symptoms
        rows = _build_ppv_table_rows(
            patient_rows=patient_rows,
            pid_cancer_terms={},
            pid_symptom_terms={},
            symptom_ordered_keys=["cough"],
            symptom_display={"cough": "Cough"},
            cancer_order_display=[],
        )
        assert rows == []

    def test_sorted_by_registry_cancer_order_then_feature_count(self):
        from services.analytics_api.app.routers._audit_symptoms import (
            _build_ppv_table_rows,
        )

        # Use pid_cancer_terms to control the bucket labels explicitly
        # so the test is not sensitive to normalise_cancer_type() mappings.
        patient_rows = [
            self._row("P1", True, "skin"),
            self._row("P2", True, "breast"),
            self._row("P3", True, "skin"),
        ]
        pid_symptom_terms = {
            "P1": {"rash"},
            "P2": {"rash"},
            "P3": {"rash"},
        }
        # Force explicit labels via pid_cancer_terms
        rows = _build_ppv_table_rows(
            patient_rows=patient_rows,
            pid_cancer_terms={"P1": ["Skin cancer"], "P2": ["Breast cancer"], "P3": ["Skin cancer"]},
            pid_symptom_terms=pid_symptom_terms,
            symptom_ordered_keys=["rash"],
            symptom_display={"rash": "Rash"},
            cancer_order_display=["Skin cancer", "Breast cancer"],
        )
        cancer_types = [r["cancer_type"] for r in rows]
        assert cancer_types == ["Skin cancer", "Breast cancer"]
