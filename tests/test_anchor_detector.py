"""Tests for services/analysis-worker/app/analyzers/anchor_detector.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestDetectReferralInText:

    def test_fast_track_referral(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _detect_referral_in_text

        text = "Fast track referral for suspected lower GI cancer"
        result = _detect_referral_in_text(text)
        assert result == "lower gastrointestinal"

    def test_2ww_referral(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _detect_referral_in_text

        text = "2ww referral to breast clinic"
        result = _detect_referral_in_text(text)
        assert result == "breast"

    def test_two_week_wait_referral(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _detect_referral_in_text

        text = "two week wait referral lung"
        result = _detect_referral_in_text(text)
        assert result == "lung"

    def test_no_referral_found(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _detect_referral_in_text

        text = "Patient presents with mild headache"
        result = _detect_referral_in_text(text)
        assert result is None


class TestNormaliseConditionType:

    def test_known_types(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _normalise_condition_type

        assert _normalise_condition_type("lower gi") == "lower gastrointestinal"
        assert _normalise_condition_type("Breast") == "breast"
        assert _normalise_condition_type("Colorectal ") == "colorectal"
        assert _normalise_condition_type("upper gi.") == "upper GI"
        assert _normalise_condition_type("urological") == "urological"

    def test_unknown_type_strips_parens(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _normalise_condition_type

        assert _normalise_condition_type("prostate (suspected)") == "prostate"

    def test_empty_string(self):
        from services.analysis_worker.app.analyzers.anchor_detector import _normalise_condition_type

        assert _normalise_condition_type("") == "unknown"


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

    def test_detects_referral_from_text(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "date": "2024-03-15", "text": "Fast track referral for suspected breast cancer"},
        ]

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(result.referral_anchors) == 1
        assert "breast" in result.referral_anchors[0]["concept_name"].lower()

    def test_detects_diagnosis_from_text(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E2", "date": "2024-05-10", "text": "Biopsy confirmed adenocarcinoma"},
        ]

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert len(result.diagnosis_anchors) == 1
        assert "adenocarcinoma" in result.diagnosis_anchors[0]["concept_name"].lower()

    def test_expand_window_sets_dates(self):
        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

        mock_client = MagicMock()
        mock_client.run.return_value = [
            {"encounter_id": "E1", "date": "2024-06-15", "text": "Fast track referral for suspected lung cancer"},
        ]

        result = detect_anchors("P1", "2024-01-01", "2024-12-31", mock_client)
        assert result.earliest_date == "2024-06-15"
        assert result.expanded_start is not None
        assert result.expanded_start < "2024-06-15"
