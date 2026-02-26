"""Tests for the Analytics API endpoints.

Covers CCI scoring, IMD postcode validation, and benchmark endpoints.
Verifies org-scoped queries use (Patient)-[:REGISTERED_AT]->(Organization) traversal.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestCCIScoring:
    """Tests for Charlson Comorbidity Index calculation."""

    @patch("services.analytics_api.app.routers.cci.PatientGraphClient")
    def test_cci_calculation_with_matches(self, MockPG):
        from services.analytics_api.app.routers.cci import calculate_cci

        instance = MockPG.return_value
        instance.run.side_effect = [
            [
                {"concept_name": "Congestive heart failure", "concept_id": "42343007", "semantic_tag": "disorder"},
                {"concept_name": "Diabetes without complications", "concept_id": "73211009", "semantic_tag": "disorder"},
                {"concept_name": "Metastatic cancer", "concept_id": "128462008", "semantic_tag": "disorder"},
            ],
            [],
        ]

        result = calculate_cci("patient-1")
        assert result["patient_id"] == "patient-1"
        assert result["cci_score"] == 1 + 1 + 2
        assert len(result["matched_conditions"]) == 3

    @patch("services.analytics_api.app.routers.cci.PatientGraphClient")
    def test_cci_no_matches(self, MockPG):
        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"concept_name": "Common cold", "concept_id": "123", "semantic_tag": "disorder"}],
            [],
        ]

        from services.analytics_api.app.routers.cci import calculate_cci
        result = calculate_cci("patient-2")
        assert result["cci_score"] == 0
        assert len(result["matched_conditions"]) == 0

    @patch("services.analytics_api.app.routers.cci.PatientGraphClient")
    def test_cci_empty_encounters(self, MockPG):
        instance = MockPG.return_value
        instance.run.side_effect = [
            [],
            [],
        ]

        from services.analytics_api.app.routers.cci import calculate_cci
        result = calculate_cci("patient-3")
        assert result["cci_score"] == 0


class TestIMDRetrieval:
    """Tests for IMD postcode validation."""

    def test_valid_postcodes(self):
        from services.analytics_api.app.routers.imd import _POSTCODE_RE

        assert _POSTCODE_RE.match("SW1A 1AA") is not None
        assert _POSTCODE_RE.match("LS1 4AP") is not None
        assert _POSTCODE_RE.match("EC1A 1BB") is not None

    def test_invalid_postcodes(self):
        from services.analytics_api.app.routers.imd import _POSTCODE_RE

        assert _POSTCODE_RE.match("invalid") is None
        assert _POSTCODE_RE.match("12345") is None


class TestBenchmarks:
    """Tests for benchmark endpoints with org filtering."""

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_kpi_benchmarks_returns_data(self, MockPG):
        instance = MockPG.return_value
        instance.run.return_value = [{
            "avg_days_to_referral": 12.5,
            "avg_days_to_diagnosis": 25.3,
            "avg_days_to_treatment": 35.1,
            "avg_consultations": 3.2,
            "episode_count": 150,
        }]

        from services.analytics_api.app.routers.benchmarks import kpi_benchmarks
        result = kpi_benchmarks(org_id=None)
        assert len(result) == 1
        assert result[0]["episode_count"] == 150

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_kpi_benchmarks_no_org_omits_registered_at(self, MockPG):
        MockPG.return_value.run.return_value = []

        from services.analytics_api.app.routers.benchmarks import kpi_benchmarks
        kpi_benchmarks(org_id=None)

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" not in query
        assert "tenantId" not in query

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_kpi_benchmarks_with_org_uses_registered_at(self, MockPG):
        MockPG.return_value.run.return_value = []

        from services.analytics_api.app.routers.benchmarks import kpi_benchmarks
        kpi_benchmarks(org_id="org-1")

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" in query
        assert "Organization" in query
        assert MockPG.return_value.run.call_args[1]["org"] == "org-1"

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_peer_comparison_uses_registered_at(self, MockPG):
        MockPG.return_value.run.return_value = []

        from services.analytics_api.app.routers.benchmarks import peer_comparison
        peer_comparison(org_id="org-1")

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" in query
        assert "Organization" in query

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_kpi_trends_with_org(self, MockPG):
        MockPG.return_value.run.return_value = []

        from services.analytics_api.app.routers.benchmarks import kpi_trends
        kpi_trends(org_id="org-1")

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" in query
        assert "tenantId" not in query

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_kpi_trends_without_org(self, MockPG):
        MockPG.return_value.run.return_value = []

        from services.analytics_api.app.routers.benchmarks import kpi_trends
        kpi_trends(org_id=None)

        query = MockPG.return_value.run.call_args[0][0]
        assert "REGISTERED_AT" not in query

    @patch("services.analytics_api.app.routers.benchmarks.PatientGraphClient")
    def test_client_always_closed(self, MockPG):
        MockPG.return_value.run.return_value = []

        from services.analytics_api.app.routers.benchmarks import kpi_benchmarks
        kpi_benchmarks(org_id=None)

        MockPG.return_value.close.assert_called_once()
