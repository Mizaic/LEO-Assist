"""Tests for libs/llm_client/topic_expansion.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.llm_client.factory import LLMResponse
from libs.llm_client.topic_expansion import (
    TopicExpansionResult,
    _normalise_terms,
    expand_topic_terms,
)


def _make_response(text: str, model_id: str = "test-model") -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=10,
        output_tokens=5,
        cached_input_tokens=0,
        stop_reason="end_turn",
        model_id=model_id,
    )


def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.converse.return_value = _make_response(response_text)
    return client


class TestNormaliseTerms:
    def test_dedupes_and_trims(self):
        assert _normalise_terms([" Cough ", "cough", "Fatigue"]) == [
            "Cough",
            "Fatigue",
        ]

    def test_rejects_non_strings_and_short(self):
        assert _normalise_terms([1, "", "x", "ok term"]) == ["ok term"]


class TestExpandTopicTerms:
    def test_empty_phrase(self):
        result = expand_topic_terms(phrase=" ")
        assert result.terms == []
        assert "empty" in result.reason.lower()

    def test_parses_terms_from_llm(self):
        client = _mock_client(
            '{"terms": ["cough", "weight loss", "haemoptysis"], '
            '"reason": "Common lung-cancer symptoms."}'
        )
        with patch(
            "libs.llm_client.topic_expansion.create_llm",
            return_value=client,
        ):
            result = expand_topic_terms(phrase="symptoms of lung cancer")
        assert isinstance(result, TopicExpansionResult)
        assert result.terms == ["cough", "weight loss", "haemoptysis"]
        assert "lung" in result.reason.lower()
        client.converse.assert_called_once()
        kwargs = client.converse.call_args.kwargs
        assert kwargs["agent_task"] == "topic_expansion"
        assert "symptoms of lung cancer" in kwargs["messages"][0]["content"]

    def test_llm_failure_returns_empty(self):
        client = MagicMock()
        client.converse.side_effect = RuntimeError("boom")
        with patch(
            "libs.llm_client.topic_expansion.create_llm",
            return_value=client,
        ):
            result = expand_topic_terms(phrase="symptoms of lung cancer")
        assert result.terms == []
        assert "could not suggest" in result.reason.lower()
