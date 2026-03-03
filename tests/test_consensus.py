"""Tests for libs/llm_client/consensus.py -- dual-model consensus runner.

Covers:
- Both models agree -> use agreed verdict
- One model fails -> use surviving model
- Both models fail -> return fail_verdict
- Disagreement triggers Sonnet arbitration
- Arbitration failure -> return fail_verdict
- Arbitration returns unparseable -> return fail_verdict
- Model IDs tracked correctly
- ConsensusResult fields set correctly
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from libs.llm_client.consensus import ConsensusResult, run_consensus
from libs.llm_client.factory import LLMResponse


def _make_response(text: str, model_id: str = "test-model") -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=10,
        output_tokens=5,
        cached_input_tokens=0,
        stop_reason="end_turn",
        model_id=model_id,
    )


def _simple_parse(text: str) -> str:
    return text.strip().lower()


class TestBothModelsAgree:

    @patch("libs.llm_client.consensus._call_provider")
    def test_agreement_returns_shared_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("YES", "haiku-id"),
            _make_response("YES", "gpt5-id"),
        ]
        result = run_consensus(
            system_prompt="test",
            user_msg="test",
            parse_fn=_simple_parse,
            fail_verdict="FAIL",
        )
        assert result.verdict == "yes"
        assert result.agreed is True
        assert result.aws_verdict == "yes"
        assert result.azure_verdict == "yes"
        assert result.arbitrator_verdict == ""

    @patch("libs.llm_client.consensus._call_provider")
    def test_agreement_tracks_model_ids(self, mock_call):
        mock_call.side_effect = [
            _make_response("yes", "haiku-v1"),
            _make_response("yes", "gpt5-mini"),
        ]
        result = run_consensus(
            system_prompt="sys",
            user_msg="msg",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert "haiku-v1" in result.model_ids
        assert "gpt5-mini" in result.model_ids
        assert len(result.model_ids) == 2


class TestOneModelFails:

    @patch("libs.llm_client.consensus._call_provider")
    def test_aws_fails_returns_azure_verdict(self, mock_call):
        mock_call.side_effect = [
            RuntimeError("AWS unavailable"),
            _make_response("correct", "gpt5"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "correct"
        assert result.azure_verdict == "correct"
        assert result.aws_verdict == ""

    @patch("libs.llm_client.consensus._call_provider")
    def test_azure_fails_returns_aws_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("active_diagnosis", "haiku"),
            RuntimeError("Azure timeout"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="uncertain",
        )
        assert result.verdict == "active_diagnosis"
        assert result.aws_verdict == "active_diagnosis"
        assert result.azure_verdict == ""

    @patch("libs.llm_client.consensus._call_provider")
    def test_aws_returns_empty_parse_uses_azure(self, mock_call):
        mock_call.side_effect = [
            _make_response("garbage!!!", "haiku"),
            _make_response("correct", "gpt5"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=lambda t: "" if "garbage" in t else t.strip(),
            fail_verdict="fail",
        )
        assert result.verdict == "correct"


class TestBothModelsFail:

    @patch("libs.llm_client.consensus._call_provider")
    def test_both_fail_returns_fail_verdict(self, mock_call):
        mock_call.side_effect = [
            RuntimeError("AWS down"),
            RuntimeError("Azure down"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="uncertain",
        )
        assert result.verdict == "uncertain"
        assert result.agreed is False
        assert "both providers failed" in result.reason

    @patch("libs.llm_client.consensus._call_provider")
    def test_both_return_empty_parse_uses_fail_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("junk", "haiku"),
            _make_response("junk", "gpt5"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=lambda _: "",
            fail_verdict="active_diagnosis",
        )
        assert result.verdict == "active_diagnosis"


class TestDisagreementArbitration:

    @patch("libs.llm_client.consensus._call_provider")
    def test_disagreement_escalates_to_sonnet(self, mock_call):
        mock_call.side_effect = [
            _make_response("yes", "haiku"),
            _make_response("no", "gpt5"),
            _make_response("yes", "sonnet"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "yes"
        assert result.agreed is False
        assert result.arbitrator_verdict == "yes"
        assert result.arbitrator_model_id == "sonnet"
        assert len(result.model_ids) == 3

    @patch("libs.llm_client.consensus._call_provider")
    def test_arbitration_picks_minority_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("active_diagnosis", "haiku"),
            _make_response("informational", "gpt5"),
            _make_response("informational", "sonnet"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="uncertain",
        )
        assert result.verdict == "informational"

    @patch("libs.llm_client.consensus._call_provider")
    def test_arbitration_failure_returns_fail_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("yes", "haiku"),
            _make_response("no", "gpt5"),
            RuntimeError("Sonnet unavailable"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="uncertain",
        )
        assert result.verdict == "uncertain"
        assert "arbitrator failed" in result.reason

    @patch("libs.llm_client.consensus._call_provider")
    def test_arbitration_empty_parse_returns_fail_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("yes", "haiku"),
            _make_response("no", "gpt5"),
            _make_response("unparseable garbage", "sonnet"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=lambda t: "" if "unparseable" in t else t.strip(),
            fail_verdict="uncertain",
        )
        assert result.verdict == "uncertain"
        assert "unparseable" in result.reason


class TestConsensusResultDefaults:

    def test_default_fields(self):
        r = ConsensusResult(verdict="test")
        assert r.confidence == 0.0
        assert r.reason == ""
        assert r.agreed is False
        assert r.model_ids == []
        assert r.arbitrator_verdict == ""
        assert r.arbitrator_model_id == ""


class TestArbitratorThirdVerdictAlert:
    """When the arbitrator returns a verdict different from both aws and azure,
    a WARNING with keyword 'consensus.arbitrator_third_verdict' must be emitted.

    This is an audit control (DC-TM-SEC-002 CONS-I-001): an unexpected third
    verdict may indicate a poisoned or jailbroken model response.
    """

    @patch("libs.llm_client.consensus._call_provider")
    def test_third_verdict_emits_warning(self, mock_call, caplog):
        """Arbitrator returns a verdict not held by either primary model."""
        import logging

        mock_call.side_effect = [
            _make_response("yes", "haiku"),
            _make_response("no", "gpt5"),
            _make_response("maybe", "sonnet"),  # third, unexpected verdict
        ]

        with caplog.at_level(logging.WARNING, logger="libs.llm_client.consensus"):
            result = run_consensus(
                system_prompt="s",
                user_msg="m",
                parse_fn=_simple_parse,
                fail_verdict="fail",
            )

        assert result.verdict == "maybe"
        assert any(
            "arbitrator_third_verdict" in r.message for r in caplog.records
        ), "Expected 'consensus.arbitrator_third_verdict' warning in log"

    @patch("libs.llm_client.consensus._call_provider")
    def test_no_warning_when_arbitrator_agrees_with_one(self, mock_call, caplog):
        """No third-verdict warning when arbitrator agrees with one primary model."""
        import logging

        mock_call.side_effect = [
            _make_response("yes", "haiku"),
            _make_response("no", "gpt5"),
            _make_response("yes", "sonnet"),  # agrees with aws
        ]

        with caplog.at_level(logging.WARNING, logger="libs.llm_client.consensus"):
            result = run_consensus(
                system_prompt="s",
                user_msg="m",
                parse_fn=_simple_parse,
                fail_verdict="fail",
            )

        assert result.verdict == "yes"
        assert not any(
            "arbitrator_third_verdict" in r.message for r in caplog.records
        ), "Must NOT warn when arbitrator agrees with a primary model"

    @patch("libs.llm_client.consensus._call_provider")
    def test_third_verdict_result_fields(self, mock_call):
        """ConsensusResult must correctly capture the third-verdict case."""
        mock_call.side_effect = [
            _make_response("active_diagnosis", "haiku"),
            _make_response("informational", "gpt5"),
            _make_response("uncertain", "sonnet"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "uncertain"
        assert result.aws_verdict == "active_diagnosis"
        assert result.azure_verdict == "informational"
        assert result.arbitrator_verdict == "uncertain"
        assert result.agreed is False
