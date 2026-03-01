"""Tests for services/analysis-worker/app/analyzers/abnormal_results.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestDetectAbnormalResults:

    def test_flags_abnormal_without_followup(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "HbA1c above upper normal range", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(flagged) == 1
        assert flagged[0]["severity"] == "warning"

    def test_no_flag_when_followup_present(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "HbA1c abnormal - repeat in 3 months", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(flagged) == 0

    def test_no_flag_for_normal_text(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "All results within normal limits", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(flagged) == 0

    def test_empty_encounters(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = []

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert flagged == []

    def test_skips_empty_text(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert flagged == []

    def test_critical_pattern_flagged(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "Critical potassium level", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(flagged) == 1

    def test_monitor_counts_as_followup(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "Low haemoglobin. Continue to monitor.", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(flagged) == 0
