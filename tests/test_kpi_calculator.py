"""Tests for services/analysis-worker/app/analyzers/kpi_calculator.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestDaysBetween:

    def test_valid_dates(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import _days_between

        assert _days_between("2024-01-01", "2024-01-15") == 14
        assert _days_between("2024-01-15", "2024-01-01") == -14

    def test_same_date(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import _days_between

        assert _days_between("2024-06-15", "2024-06-15") == 0

    def test_invalid_date(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import _days_between

        assert _days_between("not-a-date", "2024-01-01") is None
        assert _days_between("2024-01-01", "nope") is None


class TestCountConsultations:

    def test_returns_count(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import (
            _count_consultations,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = [{"cnt": 5}]

        assert _count_consultations("P1", "2024-01-01", "2024-03-01", mock_client) == 5

    def test_empty_result(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import (
            _count_consultations,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = []

        assert _count_consultations("P1", "2024-01-01", "2024-03-01", mock_client) == 0


class TestComputeEpisodeKPIs:

    def test_all_milestones_present(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import (
            _compute_episode_kpis,
        )

        milestones = {
            "first_presentation": "2024-01-01",
            "referral": "2024-01-15",
            "diagnosis": "2024-02-01",
            "treatment": "2024-03-01",
        }

        mock_client = MagicMock()
        mock_client.run.return_value = [{"cnt": 3}]

        kpis = _compute_episode_kpis("ep1", milestones, "P1", mock_client)
        metrics = {k["metric"]: k["value"] for k in kpis}

        assert metrics["days_presentation_to_referral"] == 14
        assert metrics["days_referral_to_diagnosis"] == 17
        assert metrics["days_diagnosis_to_treatment"] == 29
        assert metrics["consultations_before_referral"] == 3

    def test_partial_milestones(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import (
            _compute_episode_kpis,
        )

        milestones = {"referral": "2024-01-15"}
        mock_client = MagicMock()

        kpis = _compute_episode_kpis("ep1", milestones, "P1", mock_client)
        assert kpis == []

    def test_referral_and_diagnosis_only(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import (
            _compute_episode_kpis,
        )

        milestones = {
            "referral": "2024-01-15",
            "diagnosis": "2024-02-01",
        }
        mock_client = MagicMock()

        kpis = _compute_episode_kpis("ep1", milestones, "P1", mock_client)
        metrics = {k["metric"]: k["value"] for k in kpis}
        assert "days_referral_to_diagnosis" in metrics
        assert metrics["days_referral_to_diagnosis"] == 17


class TestCalculateKPIs:

    def test_empty_episodes(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import calculate_kpis

        mock_client = MagicMock()
        result = calculate_kpis("P1", [], mock_client)
        assert result == []

    def test_persists_kpis(self):
        from services.analysis_worker.app.analyzers.kpi_calculator import calculate_kpis

        mock_client = MagicMock()
        mock_client.run.side_effect = [
            [
                {"milestone": "referral", "earliest_date": "2024-01-15"},
                {"milestone": "diagnosis", "earliest_date": "2024-02-01"},
            ],
            [],  # persist kpi 1
        ]

        kpis = calculate_kpis("P1", ["ep1"], mock_client)
        assert len(kpis) >= 1
        assert mock_client.run.call_count >= 2
