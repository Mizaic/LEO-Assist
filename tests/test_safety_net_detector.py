"""Tests for services/analysis-worker/app/analyzers/safety_net_detector.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestCheckSafetyNetting:

    def test_safety_netting_found(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_safety_netting

        data = {
            "episode_id": "ep1",
            "encounters": [
                {"milestone_type": "first_presentation", "text": "Patient advised to safety net if symptoms persist"},
            ],
        }
        assert _check_safety_netting(data) is True

    def test_safety_netting_missing(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_safety_netting

        data = {
            "episode_id": "ep1",
            "encounters": [
                {"milestone_type": "first_presentation", "text": "Patient presents with cough"},
            ],
        }
        assert _check_safety_netting(data) is False

    def test_ignores_non_presentation_encounters(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_safety_netting

        data = {
            "episode_id": "ep1",
            "encounters": [
                {"milestone_type": "diagnosis", "text": "safety net given"},
            ],
        }
        assert _check_safety_netting(data) is False


class TestCheckInvestigationGap:

    def test_gap_detected(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_investigation_gap

        data = {
            "encounters": [
                {"milestone_type": "referral"},
            ],
        }
        result = _check_investigation_gap(data)
        assert result is not None
        assert "investigation" in result.lower()

    def test_no_gap_with_investigation(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_investigation_gap

        data = {
            "encounters": [
                {"milestone_type": "referral"},
                {"milestone_type": "investigation"},
            ],
        }
        assert _check_investigation_gap(data) is None

    def test_no_gap_without_referral(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_investigation_gap

        data = {
            "encounters": [
                {"milestone_type": "first_presentation"},
            ],
        }
        assert _check_investigation_gap(data) is None


class TestCheckReferralWait:

    def test_calculates_wait_days(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_referral_wait

        data = {
            "encounters": [
                {"milestone_type": "referral", "date": "2024-01-01"},
                {"milestone_type": "investigation", "date": "2024-01-20"},
            ],
        }
        assert _check_referral_wait(data) == 19

    def test_returns_none_without_referral(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_referral_wait

        data = {
            "encounters": [
                {"milestone_type": "investigation", "date": "2024-01-20"},
            ],
        }
        assert _check_referral_wait(data) is None

    def test_returns_none_without_specialist(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import _check_referral_wait

        data = {
            "encounters": [
                {"milestone_type": "referral", "date": "2024-01-01"},
            ],
        }
        assert _check_referral_wait(data) is None


class TestDetectSafetyNetSignals:

    def test_detects_missing_safety_netting(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import detect_safety_net_signals

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "Patient has cough", "date": "2024-01-01", "milestone_type": "first_presentation"},
        ]

        signals = detect_safety_net_signals("P1", ["ep1"], mock_client, MagicMock())
        types = [s["type"] for s in signals]
        assert "missing_safety_netting" in types

    def test_detects_excessive_wait(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import detect_safety_net_signals

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "safety net if symptoms persist", "date": "2024-01-01", "milestone_type": "referral"},
            {"encounter_id": "E2", "text": "Seen in clinic", "date": "2024-02-15", "milestone_type": "investigation"},
        ]

        signals = detect_safety_net_signals("P1", ["ep1"], mock_client, MagicMock())
        types = [s["type"] for s in signals]
        assert "excessive_referral_wait" in types

    def test_no_signals_when_compliant(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import detect_safety_net_signals

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "safety net if symptoms persist", "date": "2024-01-01", "milestone_type": "first_presentation"},
            {"encounter_id": "E2", "text": "referral", "date": "2024-01-02", "milestone_type": "referral"},
            {"encounter_id": "E3", "text": "CT scan", "date": "2024-01-10", "milestone_type": "investigation"},
        ]

        signals = detect_safety_net_signals("P1", ["ep1"], mock_client, MagicMock())
        assert len(signals) == 0

    def test_skips_empty_episode(self):
        from services.analysis_worker.app.analyzers.safety_net_detector import detect_safety_net_signals

        mock_client = MagicMock()
        mock_client.run.return_value = []

        signals = detect_safety_net_signals("P1", ["ep_empty"], mock_client, MagicMock())
        assert signals == []
