"""Tests for services/api/app/services/fix_analyzer.py."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


class TestAnalyzeCorrection:

    @patch(
        "services.api.app.services.fix_analyzer.invoke_with_fallback",
        new_callable=MagicMock,
    )
    def test_add_synonym_recommendation(self, mock_invoke):
        from services.api.app.services.fix_analyzer import analyze_correction

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "fix_type": "add_synonym",
                "domain": "symptoms",
                "resource_type": "ValueSet",
                "resource_id": "vs-symptoms",
                "change_description": "Add 'chest tightness' as synonym for 29857009",
                "change_payload": {"concept": "29857009", "synonym": "chest tightness"},
                "confidence": 85,
                "reasoning": "Common alternative phrasing",
                "auto_applicable": True,
            }
        )
        mock_invoke.return_value = mock_response

        fix = analyze_correction(
            correction_type="missing_synonym",
            correct_value="chest tightness",
            user_reason="Missed in lookup",
            proposal={
                "text": "tight chest",
                "coding": {"snomed_concept_id": "29857009"},
            },
        )

        assert fix["fix_type"] == "add_synonym"
        assert fix["confidence"] == 85
        assert fix["auto_applicable"] is True
        assert fix["status"] == "pending"
        assert fix["fix_id"].startswith("FIX_")

    @patch(
        "services.api.app.services.fix_analyzer.invoke_with_fallback",
        new_callable=MagicMock,
    )
    def test_no_fix_recommendation(self, mock_invoke):
        from services.api.app.services.fix_analyzer import analyze_correction

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "fix_type": "no_fix",
                "confidence": 90,
                "reasoning": "One-off data issue",
                "auto_applicable": False,
            }
        )
        mock_invoke.return_value = mock_response

        fix = analyze_correction(
            correction_type="wrong_encounter",
            correct_value=None,
            user_reason="Wrong patient",
            proposal={"text": "headache"},
        )

        assert fix["fix_type"] == "no_fix"
        assert fix["auto_applicable"] is False

    @patch(
        "services.api.app.services.fix_analyzer.invoke_with_fallback",
        new_callable=MagicMock,
    )
    def test_handles_invalid_json_response(self, mock_invoke):
        from services.api.app.services.fix_analyzer import analyze_correction

        mock_response = MagicMock()
        mock_response.content = "This is not JSON"
        mock_invoke.return_value = mock_response

        fix = analyze_correction(
            correction_type="missing_synonym",
            correct_value="test",
            user_reason="test",
            proposal={"text": "test"},
        )

        assert fix["fix_type"] == "no_fix"
        assert "Failed to parse" in fix["reasoning"]

    @patch(
        "services.api.app.services.fix_analyzer.invoke_with_fallback",
        new_callable=MagicMock,
    )
    def test_includes_domain_context(self, mock_invoke):
        from services.api.app.services.fix_analyzer import analyze_correction

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "fix_type": "add_code",
                "domain": "referrals",
                "resource_type": "ValueSet",
                "confidence": 70,
                "reasoning": "New concept needed",
                "auto_applicable": True,
            }
        )
        mock_invoke.return_value = mock_response

        fix = analyze_correction(
            correction_type="missing_code",
            correct_value="New concept X",
            user_reason=None,
            proposal={"text": "concept x"},
            encounter_context={"encounter_id": "E1", "text": "Encounter text"},
            domain_context={"domain": "referrals", "valueset_id": "vs-referrals"},
        )

        assert fix["fix_type"] == "add_code"

    @patch(
        "services.api.app.services.fix_analyzer.invoke_with_fallback",
        new_callable=MagicMock,
    )
    def test_update_milestone_prompt(self, mock_invoke):
        from services.api.app.services.fix_analyzer import analyze_correction

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "fix_type": "update_milestone_prompt",
                "domain": "episodes",
                "change_description": "Clarify what constitutes a first presentation",
                "confidence": 60,
                "reasoning": "Episode builder prompt is ambiguous about first presentation",
                "auto_applicable": False,
            }
        )
        mock_invoke.return_value = mock_response

        fix = analyze_correction(
            correction_type="wrong_milestone",
            correct_value="first_presentation",
            user_reason="This was the first time the patient presented, not a referral",
            proposal={"milestone_type": "referral"},
        )

        assert fix["fix_type"] == "update_milestone_prompt"
        assert fix["auto_applicable"] is False
