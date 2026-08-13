"""Tests for libs/llm-client/token_tracker.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestExtractTokenCounts:

    def test_bedrock_response_with_usage(self):
        from libs.llm_client.token_tracker import extract_token_counts

        response = MagicMock()
        response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        response.response_metadata = {
            "usage": {"cache_creation_input_tokens": 10, "cache_read_input_tokens": 5}
        }

        counts = extract_token_counts(response, "bedrock")
        assert counts["input_tokens"] == 100
        assert counts["output_tokens"] == 50
        assert counts["cache_creation_input_tokens"] == 10
        assert counts["cache_read_input_tokens"] == 5

    def test_bedrock_camel_case_cache_fields(self):
        from libs.llm_client.token_tracker import extract_token_counts

        response = MagicMock()
        response.usage_metadata = {
            "inputTokens": 80,
            "outputTokens": 40,
            "cacheWriteInputTokens": 15,
            "cacheReadInputTokens": 25,
        }
        response.response_metadata = {}

        counts = extract_token_counts(response, "bedrock")
        assert counts["input_tokens"] == 80
        assert counts["output_tokens"] == 40
        assert counts["cache_creation_input_tokens"] == 15
        assert counts["cache_read_input_tokens"] == 25

    def test_azure_response_with_usage(self):
        from libs.llm_client.token_tracker import extract_token_counts

        response = MagicMock()
        response.usage_metadata = {"input_tokens": 200, "output_tokens": 80}
        response.response_metadata = {
            "token_usage": {
                "prompt_tokens_details": {"cached_tokens": 20},
                "completion_tokens_details": {"reasoning_tokens": 5},
            }
        }

        counts = extract_token_counts(response, "azure")
        assert counts["input_tokens"] == 200
        assert counts["output_tokens"] == 80
        assert counts["input_token_details"] == {"cached_tokens": 20}
        assert counts["cache_read_input_tokens"] == 20
        assert counts["reasoning_tokens"] == 5

    def test_empty_response(self):
        from libs.llm_client.token_tracker import extract_token_counts

        response = MagicMock()
        response.usage_metadata = None
        response.response_metadata = {}

        counts = extract_token_counts(response, "bedrock")
        assert counts["input_tokens"] == 0
        assert counts["output_tokens"] == 0

    def test_dict_style_usage_metadata(self):
        from libs.llm_client.token_tracker import extract_token_counts

        response = MagicMock()
        response.usage_metadata = {"input_tokens": 42, "output_tokens": 13}
        response.response_metadata = {}

        counts = extract_token_counts(response, "bedrock")
        assert counts["input_tokens"] == 42
        assert counts["output_tokens"] == 13


class TestGetModelNames:

    def test_bedrock_arn_parsing(self):
        from libs.llm_client.token_tracker import get_model_name_from_arn

        arn = "arn:aws:bedrock:eu-west-2:123:inference-profile/eu.anthropic.claude-sonnet-4-5-v1:0"
        assert get_model_name_from_arn(arn) == "eu.anthropic.claude-sonnet-4-5-v1:0"

    def test_empty_arn(self):
        from libs.llm_client.token_tracker import get_model_name_from_arn

        assert get_model_name_from_arn("") == "unknown-bedrock"

    def test_azure_model_name(self):
        from libs.llm_client.token_tracker import get_azure_model_name

        assert get_azure_model_name("gpt-4o") == "azure-gpt-4o"


class TestTrackLLMUsage:

    @pytest.mark.asyncio
    async def test_calls_callback(self):
        from libs.llm_client.token_tracker import set_tracking_callback, track_llm_usage

        callback = MagicMock()
        set_tracking_callback(callback)
        await track_llm_usage(model_name="test", input_tokens=10)
        callback.assert_called_once_with(model_name="test", input_tokens=10)
        set_tracking_callback(None)

    @pytest.mark.asyncio
    async def test_no_callback_no_error(self):
        from libs.llm_client.token_tracker import set_tracking_callback, track_llm_usage

        set_tracking_callback(None)
        await track_llm_usage(model_name="test")

    @pytest.mark.asyncio
    async def test_callback_exception_suppressed(self):
        from libs.llm_client.token_tracker import set_tracking_callback, track_llm_usage

        def bad_callback(**kwargs):
            raise ValueError("boom")

        set_tracking_callback(bad_callback)
        await track_llm_usage(model_name="test")
        set_tracking_callback(None)
