"""Tests for the Quality Checker."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestQualityChecker:
    """Tests for the quality checker analysis."""

    @patch("libs.neo4j_client.client.PatientGraphClient")
    def test_run_with_no_data(self, MockPG):
        instance = MockPG.return_value
        instance.run.return_value = []

        from services.analysis_worker.app.analyzers.quality_checker import run_quality_checks
        report = run_quality_checks()

        assert report.total_checked == 0
        assert report.compliant_count == 0
        assert len(report.issues) == 0

    @patch("libs.neo4j_client.client.PatientGraphClient")
    def test_quality_issue_to_dict(self, MockPG):
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

    @patch("libs.neo4j_client.client.PatientGraphClient")
    def test_quality_report_to_dict(self, MockPG):
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


class TestExportService:
    """Tests for the gold data export improvements."""

    def test_context_flags_exported(self):
        """Verify context flags are included in MedSpaCy export."""
        from services.api.app.services.export_service import ExportService
        from unittest.mock import MagicMock
        import json

        mock_client = MagicMock()
        candidate = {
            "deidentified_text": "Patient has chest pain",
            "sentences": [{
                "terms": [{
                    "text": "chest pain",
                    "span_start": 12,
                    "span_end": 22,
                    "semantic_tag": "finding",
                    "context": {
                        "negated": False,
                        "uncertain": False,
                        "historical": False,
                        "subject": "patient",
                        "temporality": "present",
                    },
                    "coding": {
                        "snomed_concept_id": "29857009",
                        "snomed_term": "Chest pain",
                    },
                }],
            }],
        }

        service = ExportService(mock_client)
        with patch.object(service, "neo4j") as neo:
            session = MagicMock()
            neo.session.return_value.__enter__ = MagicMock(return_value=session)
            neo.session.return_value.__exit__ = MagicMock(return_value=False)

            with patch("services.api.app.services.export_service.list_approved_candidates", return_value=[candidate]):
                with patch("builtins.open", MagicMock()):
                    result = service.export_medspacy_training("test_export")

        assert result["entity_count"] == 1
        assert result["kb_count"] == 1
