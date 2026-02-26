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
        from services.analysis_worker.app.analyzers.quality_checker import QualityReport, QualityIssue

        report = QualityReport(total_checked=10, compliant_count=8)
        report.issues.append(QualityIssue(
            episode_id="ep-1", issue_type="outlier", severity="high",
            description="test", suggested_action="test",
        ))
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

        from services.analysis_worker.app.analyzers.quality_checker import run_quality_checks
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
            [],  # _check_unactioned_css
            [],  # _check_coding_contradictions
        ]

        from services.analysis_worker.app.analyzers.quality_checker import run_quality_checks
        report = run_quality_checks()

        assert report.total_checked == 5
        assert report.compliant_count == 5

    @patch("services.analysis_worker.app.analyzers.quality_checker.PatientGraphClient")
    def test_nhs_targets_constants(self, MockPG):
        from services.analysis_worker.app.analyzers.quality_checker import NHS_TARGETS

        assert NHS_TARGETS["faster_diagnosis_standard"] == 28
        assert NHS_TARGETS["treatment_31_day_standard"] == 31
        assert NHS_TARGETS["treatment_62_day_standard"] == 62
