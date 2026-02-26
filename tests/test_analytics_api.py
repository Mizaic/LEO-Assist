"""Tests for the Analytics API endpoints."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestCCIScoring:
    """Tests for Charlson Comorbidity Index calculation."""

    @patch("libs.neo4j_client.client.PatientGraphClient")
    def test_cci_calculation_with_matches(self, MockPG):
        from services.analytics_api.app.routers.cci import CCI_WEIGHTS

        instance = MockPG.return_value
        instance.run.side_effect = [
            [
                {"concept_name": "Congestive heart failure", "concept_id": "42343007", "semantic_tag": "disorder"},
                {"concept_name": "Diabetes without complications", "concept_id": "73211009", "semantic_tag": "disorder"},
                {"concept_name": "Metastatic cancer", "concept_id": "128462008", "semantic_tag": "disorder"},
            ],
            [],
        ]

        from services.analytics_api.app.routers.cci import calculate_cci
        result = calculate_cci("patient-1")

        assert result["patient_id"] == "patient-1"
        assert result["cci_score"] == 1 + 1 + 6  # CHF(1) + diabetes(1) + metastatic(6)
        assert len(result["matched_conditions"]) == 3

    @patch("libs.neo4j_client.client.PatientGraphClient")
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


class TestIMDRetrieval:
    """Tests for IMD postcode validation."""

    def test_invalid_postcode_regex(self):
        from services.analytics_api.app.routers.imd import _POSTCODE_RE

        assert _POSTCODE_RE.match("SW1A 1AA") is not None
        assert _POSTCODE_RE.match("LS1 4AP") is not None
        assert _POSTCODE_RE.match("invalid") is None
        assert _POSTCODE_RE.match("12345") is None


class TestBenchmarks:
    """Tests for benchmark endpoints."""

    @patch("libs.neo4j_client.client.PatientGraphClient")
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
        result = kpi_benchmarks()

        assert len(result) == 1
        assert result[0]["episode_count"] == 150
