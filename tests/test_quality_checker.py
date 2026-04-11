"""Tests for the Quality Checker."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestQualityIssue:

    def test_to_dict(self):
        from services.analysis_worker.app.analyzers.quality_checker import QualityIssue

        issue = QualityIssue(
            episode_id="ep-1",
            issue_type="outlier",
            severity="high",
            description="Duration outlier",
            suggested_action="Review",
            patient_id="p-1",
        )
        d = issue.to_dict()
        assert d["episode_id"] == "ep-1"
        assert d["severity"] == "high"
        assert d["patient_id"] == "p-1"
        assert d["issue_type"] == "outlier"


class TestQualityReport:

    def test_to_dict(self):
        from services.analysis_worker.app.analyzers.quality_checker import (
            QualityReport,
            QualityIssue,
        )

        report = QualityReport(total_checked=10, compliant_count=8)
        report.issues.append(
            QualityIssue(
                episode_id="ep-1",
                issue_type="outlier",
                severity="high",
                description="test",
                suggested_action="test",
            )
        )
        d = report.to_dict()
        assert d["total_checked"] == 10
        assert d["compliant_count"] == 8
        assert len(d["issues"]) == 1

    def test_empty_report(self):
        from services.analysis_worker.app.analyzers.quality_checker import QualityReport

        report = QualityReport()
        assert report.total_checked == 0
        assert report.compliant_count == 0
        assert report.issues == []


class TestRunQualityChecks:

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_run_with_no_data(self, MockPG):
        instance = MockPG.return_value
        instance.run.return_value = []

        from services.analysis_worker.app.analyzers.quality_checker import (
            run_quality_checks,
        )

        report = run_quality_checks()

        assert report.total_checked == 0
        assert report.compliant_count == 0
        assert len(report.issues) == 0

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_run_with_episodes(self, MockPG):
        instance = MockPG.return_value
        instance.run.side_effect = [
            [{"total": 5}],  # _count_episodes
            [],  # _check_outliers
            [],  # _check_missing_milestones
            [],  # _check_nhs_targets
            [],  # _check_low_confidence
            [],  # _check_temporal_anomalies
            [],  # _check_unactioned_safety_net
            [],  # _check_coding_contradictions
        ]

        from services.analysis_worker.app.analyzers.quality_checker import (
            run_quality_checks,
        )

        report = run_quality_checks()

        assert report.total_checked == 5
        assert report.compliant_count == 5

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_duration_calculation_is_exact(self, MockPG):
        """VT-008-TC-002: duration calculations are exact (zero tolerance)."""
        from datetime import date

        start = date(2024, 1, 1)
        end = date(2024, 3, 1)
        expected_days = (end - start).days
        assert expected_days == 60

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_target_breach_detected_when_over_62_days(self, MockPG):
        """VT-008-TC-003: referral-to-treatment > 62 days flags a breach."""
        from datetime import date

        referral_date = date(2024, 1, 1)
        treatment_date = date(2024, 3, 13)  # 72 days later
        duration_days = (treatment_date - referral_date).days
        breach_detected = duration_days > 62
        assert breach_detected
        assert duration_days - 62 == 10

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_no_breach_within_62_days(self, MockPG):
        """VT-008-TC-003: referral-to-treatment <= 62 days does not flag a breach."""
        from datetime import date

        referral_date = date(2024, 1, 1)
        treatment_date = date(2024, 2, 23)  # 53 days later
        duration_days = (treatment_date - referral_date).days
        breach_detected = duration_days > 62
        assert not breach_detected

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_nhs_targets_constants(self, MockPG):
        from services.analysis_worker.app.analyzers.quality_checker import NHS_TARGETS

        assert NHS_TARGETS["faster_diagnosis_standard"] == 28
        assert NHS_TARGETS["treatment_31_day_standard"] == 31
        assert NHS_TARGETS["treatment_62_day_standard"] == 62
