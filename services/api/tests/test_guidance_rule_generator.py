"""Tests for GuidanceRuleGenerator -- VT-LEO-AI-064.

Verifies LLM security compliance, conservative fail behaviour,
HITL gate enforcement, and audit trail creation.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from app.services.guidance_rule_generator import (
    GuidanceRuleGenerator,
    _SYSTEM_PROMPT,
    _parse_criteria_response,
)
from libs.llm_client.prompt_safety import INJECTION_GUARD


class TestLlmSecurityCompliance:
    """llm-security.mdc rules must be followed at all call sites."""

    def test_injection_guard_is_first_in_system_prompt(self):
        """INJECTION_GUARD must be the first content in every system prompt."""
        assert _SYSTEM_PROMPT.startswith(INJECTION_GUARD), (
            "INJECTION_GUARD must be prepended to _SYSTEM_PROMPT"
        )

    def test_parse_criteria_response_caps_long_responses(self):
        """_parse_criteria_response returns None for responses > 2000 chars."""
        long_response = "x" * 3000
        result = _parse_criteria_response(long_response)
        assert result is None

    def test_parse_criteria_response_handles_empty(self):
        """_parse_criteria_response returns None for empty input."""
        assert _parse_criteria_response("") is None

    def test_parse_criteria_response_returns_none_on_invalid_json(self):
        """_parse_criteria_response returns None on unparseable LLM output."""
        assert _parse_criteria_response("not json at all") is None
        assert _parse_criteria_response("{invalid}") is None

    def test_parse_criteria_response_limits_list_length(self):
        """_parse_criteria_response caps present/absent lists at 5 items."""
        response = '{"present": ["a","b","c","d","e","f","g"], "absent": []}'
        result = _parse_criteria_response(response)
        assert result is not None
        assert len(result["present"]) <= 5

    def test_parse_criteria_response_extracts_json_embedded_in_text(self):
        """parse handles JSON embedded in surrounding prose text."""
        response = 'Here is the answer: {"present": ["rectal bleeding"], "absent": []} End.'
        result = _parse_criteria_response(response)
        assert result is not None
        assert "rectal bleeding" in result["present"]

    def test_sanitise_for_prompt_imported_in_generator(self):
        """sanitise_for_prompt must be imported in guidance_rule_generator."""
        import app.services.guidance_rule_generator as mod
        assert hasattr(mod, "sanitise_for_prompt")

    def test_cap_llm_response_imported_in_generator(self):
        """cap_llm_response must be imported in guidance_rule_generator."""
        import app.services.guidance_rule_generator as mod
        assert hasattr(mod, "cap_llm_response")


class TestConservativeFail:
    """No rule should be written when the LLM consensus returns fail_verdict."""

    def _make_driver_mock(self):
        session = MagicMock()
        session.run.return_value = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=session)
        ctx.__exit__ = MagicMock(return_value=False)
        driver = MagicMock()
        driver.session.return_value = ctx
        return driver, session

    def test_no_rule_written_when_consensus_returns_none(self):
        """When consensus verdict is None, no rule node is written to Neo4j."""
        driver, session = self._make_driver_mock()

        from libs.llm_client.consensus import ConsensusResult
        mock_result = ConsensusResult(verdict=None)

        recs = [{"id": "NG151:R000", "verbatim": "Refer for rectal bleeding.", "title": "Refer", "urgency": "urgent_2w", "strength": "refer"}]
        session.run.return_value = iter([dict(r) for r in recs])

        generator = GuidanceRuleGenerator(driver)

        with patch("app.services.guidance_rule_generator.run_consensus", return_value=mock_result):
            with patch.object(generator, "_fetch_recommendations", return_value=recs):
                result = generator.generate_rules_for_guideline("NG151")

        assert result == [], "No rules should be generated on consensus failure"

    def test_no_rule_written_when_verbatim_is_empty(self):
        """No rule is generated for recommendations with empty verbatim text."""
        driver, _ = self._make_driver_mock()
        generator = GuidanceRuleGenerator(driver)
        empty_rec = {"id": "NG151:R001", "verbatim": "", "title": "", "urgency": "", "strength": ""}

        with patch.object(generator, "_fetch_recommendations", return_value=[empty_rec]):
            result = generator.generate_rules_for_guideline("NG151")

        assert result == []


class TestHitlGate:
    """All generated rules must start with status pending_review."""

    def _make_driver_mock(self):
        session = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=session)
        ctx.__exit__ = MagicMock(return_value=False)
        driver = MagicMock()
        driver.session.return_value = ctx
        return driver, session

    def test_generated_rules_have_pending_review_status(self):
        """Generated rules are written with status: pending_review."""
        driver, session = self._make_driver_mock()
        session.run.return_value = MagicMock()

        from libs.llm_client.consensus import ConsensusResult
        criteria = {"present": ["rectal bleeding"], "absent": ["known bowel disease"]}
        mock_result = ConsensusResult(verdict=criteria)

        rec = {"id": "NG151:R000", "verbatim": "Refer patients with rectal bleeding.", "title": "Refer", "urgency": "urgent_2w", "strength": "refer"}

        generator = GuidanceRuleGenerator(driver)

        with patch("app.services.guidance_rule_generator.run_consensus", return_value=mock_result):
            with patch.object(generator, "_fetch_recommendations", return_value=[rec]):
                with patch("app.services.guidance_rule_generator._snomed_lookup_sync", return_value=None):
                    generator.generate_rules_for_guideline("NG151")

        upsert_calls = [c for c in session.run.call_args_list if "pending_review" in str(c)]
        assert len(upsert_calls) > 0, "At least one Cypher call must set status: pending_review"

    def test_review_task_created_for_each_rule(self):
        """A GuidanceReviewTask node is created for each generated rule."""
        driver, session = self._make_driver_mock()
        session.run.return_value = MagicMock()

        from libs.llm_client.consensus import ConsensusResult
        criteria = {"present": ["symptom"], "absent": []}
        mock_result = ConsensusResult(verdict=criteria)

        rec = {"id": "NG151:R000", "verbatim": "Test recommendation.", "title": "Test", "urgency": "routine", "strength": "offer"}

        generator = GuidanceRuleGenerator(driver)
        with patch("app.services.guidance_rule_generator.run_consensus", return_value=mock_result):
            with patch.object(generator, "_fetch_recommendations", return_value=[rec]):
                with patch("app.services.guidance_rule_generator._snomed_lookup_sync", return_value=None):
                    generator.generate_rules_for_guideline("NG151")

        task_calls = [c for c in session.run.call_args_list if "GuidanceReviewTask" in str(c)]
        assert len(task_calls) > 0, "A GuidanceReviewTask must be created for HITL queue"
