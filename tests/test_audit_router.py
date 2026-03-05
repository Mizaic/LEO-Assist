"""Unit tests for the NCDA audit analytics router.

Tests focus on data-shaping logic (pct calculations, interval stats,
multi-scope envelope) without requiring a live Neo4j connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_scope(is_admin: bool = True, primary_org_id=None):
    scope = MagicMock()
    scope.is_admin = is_admin
    scope.primary_org_id = primary_org_id
    scope.org_ids = []
    scope.to_query_params.return_value = {}
    return scope


def _mock_client(rows_by_call):
    """Return a mock PatientGraphClient where .run() returns successive values."""
    mock = MagicMock()
    mock.run.side_effect = rows_by_call
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# Multi-scope response helpers
def _practice(result):
    return result["scopes"]["practice"]

def _alliance(result):
    return result["scopes"]["alliance_live"]

def _england(result):
    return result["scopes"]["england_live"]

def _benchmark(result):
    return result.get("benchmark")


# ---------------------------------------------------------------------------
# Tests: _q_cancer_type / audit_cancer_type
# ---------------------------------------------------------------------------

class TestAuditCancerType:
    """Tests for cancer type section multi-scope envelope."""

    def test_returns_multi_scope_envelope(self):
        rows = [
            {"cancer_type": "breast", "n": 14},
            {"cancer_type": "colorectal", "n": 8},
        ]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        assert "practice" in result["scopes"]
        assert "alliance_live" in result["scopes"]
        assert "england_live" in result["scopes"]
        assert "benchmark" in result

    def test_pct_sums_to_100(self):
        rows = [
            {"cancer_type": "breast", "n": 30},
            {"cancer_type": "colorectal", "n": 20},
            {"cancer_type": "lung", "n": 50},
        ]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        practice_data = _practice(result)
        total_pct = sum(r["pct"] for r in practice_data)
        assert abs(total_pct - 100.0) < 1.0

    def test_empty_returns_empty_practice(self):
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([[]])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert _practice(result) == []
        assert _alliance(result) is None
        assert _england(result) is None

    def test_no_org_selected_alliance_and_england_are_none(self):
        rows = [{"cancer_type": "breast", "n": 10}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert _alliance(result) is None
        assert _england(result) is None


# ---------------------------------------------------------------------------
# Tests: _q_consultations
# ---------------------------------------------------------------------------

class TestAuditConsultations:
    """Tests for GET /analytics/audit/consultations multi-scope envelope.

    _q_consultations makes 2 DB calls: summary row + per-episode rows.
    """

    def test_multi_scope_envelope_present(self):
        summary_rows = [{"fewer_than_3": 10, "three_or_more": 5, "total_episodes": 15, "avg_consultations": 2.0}]
        per_ep_rows = [{"consult_count": 1}, {"consult_count": 3}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([summary_rows, per_ep_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_consultations
            result = audit_consultations(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        practice = _practice(result)
        assert "fewer_than_3_pct" in practice
        assert "three_or_more_pct" in practice

    def test_percentages_sum_to_100(self):
        summary_rows = [{"fewer_than_3": 42, "three_or_more": 9, "total_episodes": 51, "avg_consultations": 1.5}]
        per_ep_rows = []
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([summary_rows, per_ep_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_consultations
            result = audit_consultations(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        practice = _practice(result)
        assert practice["fewer_than_3_pct"] == round(42 * 100.0 / 51, 1)
        assert practice["three_or_more_pct"] == round(9 * 100.0 / 51, 1)


# ---------------------------------------------------------------------------
# Tests: interval stats computation (pure logic)
# ---------------------------------------------------------------------------

class TestIntervalStats:
    """Tests that median / IQR helpers produce correct values."""

    def test_median_even_list(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        n = len(vals)
        expected = (vals[n // 2 - 1] + vals[n // 2]) / 2  # 5.5

        def _median(v):
            if not v:
                return None
            k = len(v)
            return v[k // 2] if k % 2 else (v[k // 2 - 1] + v[k // 2]) / 2

        assert _median(vals) == expected

    def test_median_odd_list(self):
        vals = [1, 2, 3, 4, 5]

        def _median(v):
            if not v:
                return None
            k = len(v)
            return v[k // 2] if k % 2 else (v[k // 2 - 1] + v[k // 2]) / 2

        assert _median(vals) == 3

    def test_empty_patients_returns_none_stats(self):
        agg_rows = [{"pci_n": 0, "mean_pci": None, "di_n": 0, "mean_di": None}]
        patient_rows: list = []

        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([agg_rows, patient_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_intervals
            result = audit_intervals(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        practice = _practice(result)
        assert practice["pci"]["median"] is None
        assert practice["di"]["median"] is None
        assert practice["patients"] == []


# ---------------------------------------------------------------------------
# Tests: safety_netting
# ---------------------------------------------------------------------------

class TestAuditSafetyNetting:
    def test_multi_scope_envelope(self):
        rows = [{"total_episodes": 51, "recorded": 10}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_safety_netting
            result = audit_safety_netting(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        practice = _practice(result)
        assert "recorded_pct" in practice
        assert practice["recorded_pct"] == round(10 * 100.0 / 51, 1)


# ---------------------------------------------------------------------------
# Tests: avoidable_delays
# ---------------------------------------------------------------------------

class TestAuditAvoidableDelays:
    def test_multi_scope_envelope(self):
        rows = [{"total_episodes": 51, "has_delay": 14, "before_pres": 9, "pres_to_ref": 4, "after_ref": 1}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_avoidable_delays
            result = audit_avoidable_delays(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        practice = _practice(result)
        assert "avoidable_delay_pct" in practice
        assert practice["avoidable_delay_pct"] == round(14 * 100.0 / 51, 1)


# ---------------------------------------------------------------------------
# Tests: benchmark_category fetch helper
# ---------------------------------------------------------------------------

class TestFetchBenchmarkMetrics:
    """Tests for _fetch_benchmark_metrics ODS linkage logic."""

    def test_practice_matched_by_ods_code(self):
        set_rows = [{"set_name": "NCDA 2018"}]
        value_rows = [
            {"metric_id": "primary_care_interval.median_days", "scope_type": "gp_practice",
             "scope_id": "C84070", "scope_name": "Woodbrook Medical Centre", "value": 30},
            {"metric_id": "primary_care_interval.median_days", "scope_type": "national",
             "scope_id": "england", "scope_name": "England", "value": 25},
        ]

        with patch("services.analytics_api.app.routers.audit.KnowledgeGraphClient") as MockKG:
            mock_kg = MagicMock()
            mock_kg.run.side_effect = [set_rows, value_rows]
            MockKG.return_value = mock_kg

            from services.analytics_api.app.routers.audit import _fetch_benchmark_metrics
            result = _fetch_benchmark_metrics(
                "ncda-2018", "primary_care_interval",
                org_id="woodbrook-gp", org_ods_code="C84070", alliance_id=None,
            )

        assert result is not None
        metrics = result["metrics"]
        assert "primary_care_interval.median_days" in metrics
        m = metrics["primary_care_interval.median_days"]
        assert m["practice"] == 30
        assert m["national"] == 25

    def test_no_values_returns_none(self):
        set_rows = [{"set_name": "NCDA 2018"}]
        with patch("services.analytics_api.app.routers.audit.KnowledgeGraphClient") as MockKG:
            mock_kg = MagicMock()
            mock_kg.run.side_effect = [set_rows, []]
            MockKG.return_value = mock_kg

            from services.analytics_api.app.routers.audit import _fetch_benchmark_metrics
            result = _fetch_benchmark_metrics("ncda-2018", "primary_care_interval")

        assert result is None
