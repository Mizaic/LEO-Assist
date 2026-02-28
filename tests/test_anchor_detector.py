"""Tests for services/analysis-worker/app/analyzers/anchor_detector.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAnchorResult:

    def test_has_referral_empty(self):
        from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

        result = AnchorResult(patient_id="P1")
        assert not result.has_referral

    def test_has_referral_with_data(self):
        from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

        result = AnchorResult(patient_id="P1", referral_anchors=[{"x": 1}])
        assert result.has_referral


class TestDetectAnchors:

    def test_no_encounters(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = []

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert result.patient_id == "P1"
        assert result.referral_anchors == []
        assert result.diagnosis_anchors == []

    def test_detects_referral_from_documents(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {
                "encounter_id": "E1",
                "encounter_date": "2024-03-15",
                "concept_id": 276281000000104,
                "concept_name": "Fast track referral for suspected breast cancer",
                "semantic_tag": "procedure",
                "source": "documents",
                "confidence": 0.95,
                "evidence": "Fast track referral for suspected breast cancer",
            },
        ]

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(result.referral_anchors) == 1
        assert "breast" in result.referral_anchors[0]["concept_name"].lower()

    def test_detects_diagnosis_from_documents(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {
                "encounter_id": "E2",
                "encounter_date": "2024-05-10",
                "concept_id": 363367000,
                "concept_name": "Malignant tumour of colon",
                "semantic_tag": "disorder",
                "source": "documents",
                "confidence": 0.93,
                "evidence": "Biopsy confirmed adenocarcinoma",
            },
        ]

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(result.diagnosis_anchors) == 1
        assert "malignant" in result.diagnosis_anchors[0]["concept_name"].lower()

    def test_expand_window_sets_dates(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {
                "encounter_id": "E1",
                "encounter_date": "2024-06-15",
                "concept_id": 276431000000102,
                "concept_name": "Fast track referral for suspected lung cancer",
                "semantic_tag": "procedure",
                "source": "documents",
                "confidence": 0.94,
                "evidence": "Fast track referral for suspected lung cancer",
            },
        ]

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert result.earliest_date == "2024-06-15"
        assert result.expanded_start is not None
        assert result.expanded_start < "2024-06-15"
