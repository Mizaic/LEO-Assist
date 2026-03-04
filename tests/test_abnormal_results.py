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

    def test_sensitivity_meets_95_pct_on_mock_dataset(self):
        """VT-005-TC-003: sensitivity >= 95% — all known abnormals detected."""
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        known_abnormals = [
            "HbA1c above upper normal range",
            "Critical potassium level",
            "eGFR below 30 — severely reduced kidney function",
            "Haemoglobin critically low",
        ]
        known_normals = [
            "All results within normal limits",
            "Blood pressure within range",
        ]

        detected = 0
        for text in known_abnormals:
            mock_client = MagicMock()
            mock_client.run.return_value = [
                {"encounter_id": "E1", "text": text, "date": "2024-01-01"}
            ]
            flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
            if flagged:
                detected += 1

        sensitivity = detected / len(known_abnormals)
        assert sensitivity >= 0.95, f"Sensitivity {sensitivity:.0%} below 95% threshold"

    def test_no_severe_abnormal_missed(self):
        """VT-005-TC-003: severe abnormals (critical) must never be missed."""
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        critical_texts = ["Critical potassium level", "Haemoglobin critically low"]

        for text in critical_texts:
            mock_client = MagicMock()
            mock_client.run.return_value = [
                {"encounter_id": "E1", "text": text, "date": "2024-01-01"}
            ]
            flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
            assert flagged, f"Critical abnormal '{text}' was not detected (false negative)"

    def test_monitor_counts_as_followup(self):
        from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "text": "Low haemoglobin. Continue to monitor.", "date": "2024-03-01"},
        ]

        flagged = detect_abnormal_results("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(flagged) == 0
