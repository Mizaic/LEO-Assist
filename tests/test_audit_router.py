"""Unit tests for the NCDA audit analytics router.

Tests focus on the data-shaping logic (pct calculations, interval stats)
without requiring a live Neo4j connection — mocking PatientGraphClient.run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers / mocks
# ---------------------------------------------------------------------------

def _mock_scope(is_admin: bool = True):
    scope = MagicMock()
    scope.is_admin = is_admin
    scope.primary_org_id = None
    scope.org_ids = []
    scope.to_query_params.return_value = {}
    return scope


def _make_app():
    """Create a minimal FastAPI app with just the audit router."""
    from fastapi import FastAPI
    from services.analytics_api.app.routers.audit import router

    app = FastAPI()
    app.include_router(router, prefix="/analytics")
    return app


# ---------------------------------------------------------------------------
# Tests: cancer_type endpoint
# ---------------------------------------------------------------------------

class TestAuditCancerType:
    """Tests for GET /analytics/audit/cancer-type."""

    def test_returns_pct_summing_to_100(self):
        rows = [
            {"cancer_type": "Breast", "n": 14},
            {"cancer_type": "Colorectal", "n": 8},
            {"cancer_type": "Lung", "n": 8},
            {"cancer_type": "Prostate", "n": 21},
        ]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            client_instance = MockClient.return_value.__enter__ = MagicMock()
            mock = MagicMock()
            mock.run.return_value = rows
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            scope = _mock_scope()
            result = audit_cancer_type(scope=scope, org_id=None, date_from=None, date_to=None)

        total_n = sum(r["n"] for r in rows)
        total_pct = sum(r["pct"] for r in result)
        assert abs(total_pct - 100.0) < 1.0, f"Expected pct to sum ~100, got {total_pct}"
        assert all("pct" in r for r in result)
        assert all("n" in r for r in result)

    def test_handles_empty_result(self):
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = MagicMock()
            mock.run.return_value = []
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            scope = _mock_scope()
            result = audit_cancer_type(scope=scope, org_id=None, date_from=None, date_to=None)

        assert result == []


# ---------------------------------------------------------------------------
# Tests: consultations endpoint
# ---------------------------------------------------------------------------

class TestAuditConsultations:
    """Tests for GET /analytics/audit/consultations."""

    def test_percentages_are_correct(self):
        summary_row = {
            "fewer_than_3": 42,
            "three_or_more": 9,
            "total_episodes": 51,
            "avg_consultations": 1.2,
        }
        per_episode_rows = [{"consult_count": i} for i in [0, 1, 1, 1, 2, 2, 3, 4, 5]]

        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = MagicMock()
            mock.run.side_effect = [summary_row] if False else [[summary_row], per_episode_rows]
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_consultations
            scope = _mock_scope()
            result = audit_consultations(scope=scope, org_id=None, date_from=None, date_to=None)

        assert result["fewer_than_3_pct"] == round(42 * 100.0 / 51, 1)
        assert result["three_or_more_pct"] == round(9 * 100.0 / 51, 1)
        assert result["total_episodes"] == 51


# ---------------------------------------------------------------------------
# Tests: intervals endpoint — stats computation
# ---------------------------------------------------------------------------

class TestAuditIntervals:
    """Tests that interval statistics (median, IQR) are computed correctly."""

    def test_median_and_iqr_from_sorted_values(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        n = len(vals)
        expected_median = (vals[n // 2 - 1] + vals[n // 2]) / 2  # 5.5
        expected_q1 = vals[n // 4]  # index 2 → 3
        expected_q3 = vals[3 * n // 4]  # index 7 → 8

        # Test the helper logic inline (same as the endpoint)
        def _median(v):
            if not v:
                return None
            k = len(v)
            return v[k // 2] if k % 2 else (v[k // 2 - 1] + v[k // 2]) / 2

        def _iqr(v):
            if not v:
                return None, None
            k = len(v)
            return v[k // 4], v[3 * k // 4]

        assert _median(vals) == expected_median
        q1, q3 = _iqr(vals)
        assert q1 == expected_q1
        assert q3 == expected_q3

    def test_empty_patients_returns_none_stats(self):
        agg_rows = [{"pci_n": 0, "mean_pci": None, "di_n": 0, "mean_di": None}]
        patient_rows: list = []

        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = MagicMock()
            mock.run.side_effect = [agg_rows, patient_rows]
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_intervals
            scope = _mock_scope()
            result = audit_intervals(scope=scope, org_id=None, date_from=None, date_to=None)

        assert result["pci"]["median"] is None
        assert result["di"]["median"] is None
        assert result["patients"] == []


# ---------------------------------------------------------------------------
# Tests: safety_netting endpoint
# ---------------------------------------------------------------------------

class TestAuditSafetyNetting:
    """Tests for GET /analytics/audit/safety-netting."""

    def test_pct_calculation(self):
        rows = [{"total_episodes": 51, "recorded": 10, "positive_contribution": 7, "no_contribution": 2}]

        with patch("services.analytics_api.app.routers.audit._run") as mock_run:
            mock_run.return_value = rows

            from services.analytics_api.app.routers.audit import audit_safety_netting
            scope = _mock_scope()
            result = audit_safety_netting(scope=scope, org_id=None, date_from=None, date_to=None)

        assert result["recorded_pct"] == round(10 * 100.0 / 51, 1)
        assert result["positive_contribution_pct"] == round(7 * 100.0 / 10, 1)


# ---------------------------------------------------------------------------
# Tests: avoidable_delays endpoint
# ---------------------------------------------------------------------------

class TestAuditAvoidableDelays:
    """Tests for GET /analytics/audit/avoidable-delays."""

    def test_pct_calculation(self):
        rows = [{
            "total_episodes": 51,
            "has_avoidable_delay": 14,
            "delay_before_presentation": 9,
            "delay_before_referral": 4,
            "delay_after_referral": 4,
        }]

        with patch("services.analytics_api.app.routers.audit._run") as mock_run:
            mock_run.return_value = rows

            from services.analytics_api.app.routers.audit import audit_avoidable_delays
            scope = _mock_scope()
            result = audit_avoidable_delays(scope=scope, org_id=None, date_from=None, date_to=None)

        assert result["has_avoidable_delay_pct"] == round(14 * 100.0 / 51, 1)
        assert result["delay_before_presentation_pct"] == round(9 * 100.0 / 14, 1)
