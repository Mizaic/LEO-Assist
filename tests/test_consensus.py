"""Tests for libs/llm_client/consensus.py.

run_consensus defaults to a single Bedrock call (with parse-retry). When
CONSENSUS_DUAL_MODEL=true it runs AWS + Azure small-tier in parallel and
arbitrates disagreements with a big-tier AWS model.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

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


class TestRunConsensusSuccess:
    @patch("libs.llm_client.consensus._call_provider")
    def test_returns_parsed_verdict(self, mock_call):
        mock_call.return_value = _make_response("YES", "haiku-v1")
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "yes"
        assert result.aws_verdict == "yes"
        assert result.agreed is True
        assert result.azure_verdict == ""
        assert result.arbitrator_verdict == ""
        assert "haiku-v1" in result.model_ids
        assert mock_call.call_count == 1

    @patch("libs.llm_client.consensus._call_provider")
    def test_tier_override_passed_through(self, mock_call):
        mock_call.return_value = _make_response("ok", "mid")
        run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
            tier="small",
        )
        assert mock_call.call_args[0][1] == "small"


class TestParseRetry:
    @patch("libs.llm_client.consensus._call_provider")
    def test_empty_parse_triggers_second_call(self, mock_call):
        mock_call.side_effect = [
            _make_response("garbage", "m1"),
            _make_response("correct", "m2"),
        ]

        def parse_fn(t: str) -> str:
            return "" if "garbage" in t else t.strip().lower()

        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=parse_fn,
            fail_verdict="fail",
        )
        assert result.verdict == "correct"
        assert mock_call.call_count == 2

    @patch("libs.llm_client.consensus._call_provider")
    def test_parse_retry_logs_warning(self, mock_call, caplog):
        mock_call.side_effect = [
            _make_response("bad", "m1"),
            _make_response("good", "m2"),
        ]

        def parse_fn(t: str) -> str:
            return "" if t == "bad" else "yes"

        with caplog.at_level(logging.WARNING, logger="libs.llm_client.consensus"):
            run_consensus(
                system_prompt="s",
                user_msg="m",
                parse_fn=parse_fn,
                fail_verdict="fail",
            )
        assert any("parse failed" in r.message for r in caplog.records)


class TestRunConsensusFailure:
    @patch("libs.llm_client.consensus._call_provider")
    def test_provider_exception_returns_fail_verdict(self, mock_call):
        mock_call.side_effect = RuntimeError("bedrock down")
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="uncertain",
        )
        assert result.verdict == "uncertain"
        assert result.agreed is False
        assert "call/parse failed" in result.reason

    @patch("libs.llm_client.consensus._call_provider")
    def test_unparseable_after_retry_returns_fail_verdict(self, mock_call):
        mock_call.side_effect = [
            _make_response("junk1", "a"),
            _make_response("junk2", "b"),
        ]
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=lambda _: "",
            fail_verdict="active_diagnosis",
        )
        assert result.verdict == "active_diagnosis"
        assert mock_call.call_count == 2


class TestConsensusResultDefaults:
    def test_default_fields(self):
        r = ConsensusResult(verdict="test")
        assert r.confidence == 0.0
        assert r.reason == ""
        assert r.agreed is False
        assert r.model_ids == []
        assert r.arbitrator_verdict == ""
        assert r.arbitrator_model_id == ""


class TestDualModelConsensus:
    """CONSENSUS_DUAL_MODEL=true runs AWS+Azure small, arbitrates with big."""

    @patch.dict("os.environ", {"CONSENSUS_DUAL_MODEL": "true"}, clear=False)
    @patch("libs.llm_client.consensus._call_provider")
    def test_agreement_short_circuits_without_arbitrator(self, mock_call):
        def route(provider, tier, *_args, **_kwargs):
            return _make_response("yes", f"{provider}-{tier}")

        mock_call.side_effect = route
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "yes"
        assert result.agreed is True
        assert result.aws_verdict == "yes"
        assert result.azure_verdict == "yes"
        assert result.arbitrator_verdict == ""
        assert mock_call.call_count == 2

    @patch.dict(
        "os.environ",
        {"CONSENSUS_DUAL_MODEL": "true", "CONSENSUS_AWS_TIER": "big"},
        clear=False,
    )
    @patch("libs.llm_client.consensus._call_provider")
    def test_disagreement_triggers_arbitrator(self, mock_call):
        def route(provider, tier, *_args, **_kwargs):
            if tier == "small" and provider == "aws":
                return _make_response("yes", "aws-small")
            if tier == "small" and provider == "azure":
                return _make_response("no", "az-small")
            return _make_response("yes", "aws-big")

        mock_call.side_effect = route
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "yes"
        assert result.agreed is False
        assert result.arbitrator_verdict == "yes"
        assert result.arbitrator_model_id == "aws-big"
        assert mock_call.call_count == 3

    @patch.dict("os.environ", {"CONSENSUS_DUAL_MODEL": "true"}, clear=False)
    @patch("libs.llm_client.consensus._call_provider")
    def test_single_provider_failure_promotes_arbitrator(self, mock_call):
        def route(provider, tier, *_args, **_kwargs):
            if tier == "small" and provider == "azure":
                raise RuntimeError("azure down")
            if tier == "small" and provider == "aws":
                return _make_response("yes", "aws-small")
            return _make_response("yes", "aws-big")

        mock_call.side_effect = route
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert result.verdict == "yes"
        assert result.single_model_fallback is True
        assert result.arbitrator_verdict == "yes"

    @patch.dict("os.environ", {"CONSENSUS_DUAL_MODEL": "true"}, clear=False)
    @patch("libs.llm_client.consensus._call_provider")
    def test_all_providers_fail_returns_fail_verdict(self, mock_call):
        mock_call.side_effect = RuntimeError("everything is on fire")
        result = run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="gate_failed",
        )
        assert result.verdict == "gate_failed"
        assert result.agreed is False


class TestSingleModelIsDefault:
    @patch.dict("os.environ", {"CONSENSUS_DUAL_MODEL": "false"}, clear=False)
    @patch("libs.llm_client.consensus._call_provider")
    def test_no_azure_call_in_default_mode(self, mock_call):
        mock_call.return_value = _make_response("yes", "aws-big")
        run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert mock_call.call_count == 1
        assert mock_call.call_args[0][0] == "aws"

    @patch.dict(
        "os.environ",
        {
            "CONSENSUS_DUAL_MODEL": "false",
            "PIPELINE_CONSENSUS_MODE": "false",
            "CONSENSUS_AWS_TIER": "",
            "PIPELINE_MODEL_TIER": "small",
        },
        clear=False,
    )
    @patch("libs.llm_client.consensus._call_provider")
    def test_default_tier_is_small_haiku(self, mock_call):
        mock_call.return_value = _make_response("yes", "haiku")
        run_consensus(
            system_prompt="s",
            user_msg="m",
            parse_fn=_simple_parse,
            fail_verdict="fail",
        )
        assert mock_call.call_args[0][1] == "small"
