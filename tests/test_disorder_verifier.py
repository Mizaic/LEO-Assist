"""Tests for libs/llm_client/disorder_verifier.py.

Covers:
- _parse_verdict: JSON extraction, markdown-wrapped JSON, invalid input
- _fail_verdict_for_mode: HITL vs autonomous fail-safe behaviour
- verify_disorder: end-to-end with mocked consensus
- Unknown verdict falls back to mode-appropriate fail_verdict
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from libs.llm_client.consensus import ConsensusResult
from libs.llm_client.disorder_verifier import (
    DisorderVerdict,
    _fail_verdict_for_mode,
    _parse_verdict,
    verify_disorder,
)


class TestParseVerdict:

    def test_plain_json(self):
        raw = json.dumps({"verdict": "active_diagnosis", "reason": "confirmed"})
        assert _parse_verdict(raw) == "active_diagnosis"

    def test_markdown_wrapped_json(self):
        raw = '```json\n{"verdict": "informational", "reason": "test"}\n```'
        assert _parse_verdict(raw) == "informational"

    def test_json_with_surrounding_text(self):
        raw = 'Here is my analysis: {"verdict": "historical", "reason": "old"} end.'
        assert _parse_verdict(raw) == "historical"

    def test_missing_verdict_key(self):
        raw = json.dumps({"reason": "no verdict here"})
        assert _parse_verdict(raw) == ""

    def test_empty_verdict_value(self):
        raw = json.dumps({"verdict": "", "reason": "blank"})
        assert _parse_verdict(raw) == ""

    def test_totally_invalid_input(self):
        assert _parse_verdict("this is not json at all") == ""

    def test_empty_string(self):
        assert _parse_verdict("") == ""

    def test_whitespace_stripping(self):
        raw = json.dumps({"verdict": "  uncertain  "})
        assert _parse_verdict(raw) == "uncertain"


class TestFailVerdictForMode:

    def test_hitl_defaults_to_active_diagnosis(self):
        assert _fail_verdict_for_mode("hitl") == "active_diagnosis"

    def test_autonomous_defaults_to_uncertain(self):
        assert _fail_verdict_for_mode("autonomous") == "uncertain"

    def test_unknown_mode_defaults_to_active_diagnosis(self):
        assert _fail_verdict_for_mode("unknown") == "active_diagnosis"


class TestVerifyDisorderEndToEnd:

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_active_diagnosis_hitl(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="active_diagnosis",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_disorder(
            "Type 2 diabetes",
            "Patient has Type 2 diabetes, well controlled.",
            coding_mode="hitl",
        )
        assert result == DisorderVerdict.ACTIVE_DIAGNOSIS
        call_kwargs = mock_consensus.call_args.kwargs
        assert call_kwargs["fail_verdict"] == "active_diagnosis"

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_informational_autonomous(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="informational",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_disorder(
            "CKD",
            "eGFR for CKD monitoring",
            coding_mode="autonomous",
        )
        assert result == DisorderVerdict.INFORMATIONAL
        call_kwargs = mock_consensus.call_args.kwargs
        assert call_kwargs["fail_verdict"] == "uncertain"

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_historical_verdict(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="historical",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_disorder("asthma", "H/O asthma")
        assert result == DisorderVerdict.HISTORICAL

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_uncertain_verdict(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="uncertain",
            agreed=False,
            model_ids=["haiku", "gpt5", "sonnet"],
        )
        result = verify_disorder("?CKD", "Query CKD stage 3")
        assert result == DisorderVerdict.UNCERTAIN

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_unknown_verdict_hitl_falls_back(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="some_random_garbage",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_disorder("diabetes", "test", coding_mode="hitl")
        assert result == DisorderVerdict.ACTIVE_DIAGNOSIS

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_unknown_verdict_autonomous_falls_back(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="some_random_garbage",
            agreed=True,
            model_ids=["haiku", "gpt5"],
        )
        result = verify_disorder("diabetes", "test", coding_mode="autonomous")
        assert result == DisorderVerdict.UNCERTAIN

    @patch("libs.llm_client.disorder_verifier.run_consensus")
    def test_encounter_text_truncated_to_2000(self, mock_consensus):
        mock_consensus.return_value = ConsensusResult(
            verdict="active_diagnosis",
            agreed=True,
            model_ids=["h"],
        )
        long_text = "x" * 5000
        verify_disorder("test", long_text)
        call_kwargs = mock_consensus.call_args.kwargs
        user_msg = json.loads(call_kwargs["user_msg"])
        assert len(user_msg["encounter_text"]) == 2000


class TestDisorderVerifierPromptRules:
    """Verify that the disorder verifier prompt includes lab-value safety rules."""

    def test_prompt_contains_lab_value_rule(self):
        from libs.llm_client.disorder_verifier import _SYSTEM_PROMPT

        assert "CKD-EPI" in _SYSTEM_PROMPT
        assert "formula name" in _SYSTEM_PROMPT

    def test_prompt_forbids_lab_value_as_active_diagnosis(self):
        from libs.llm_client.disorder_verifier import _SYSTEM_PROMPT

        assert "Do NOT classify a lab value as active_diagnosis" in _SYSTEM_PROMPT

    def test_prompt_mentions_observation_not_diagnosis(self):
        from libs.llm_client.disorder_verifier import _SYSTEM_PROMPT

        assert "observation" in _SYSTEM_PROMPT.lower()
        assert "NOT a diagnosis" in _SYSTEM_PROMPT
