"""Tests for libs/llm-client/providers.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInvokeWithRetry:

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        from libs.llm_client.providers import invoke_with_retry

        model = AsyncMock()
        model.ainvoke.return_value = "response"
        result = await invoke_with_retry(model, ["msg"], max_retries=3)
        assert result == "response"
        model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self):
        from libs.llm_client.providers import invoke_with_retry
        from urllib3.exceptions import ReadTimeoutError

        model = AsyncMock()
        model.ainvoke.side_effect = [
            ReadTimeoutError(None, None, "timeout"),
            "ok",
        ]

        with patch("libs.llm_client.providers.asyncio.sleep", new_callable=AsyncMock):
            result = await invoke_with_retry(model, ["msg"], max_retries=3)
        assert result == "ok"
        assert model.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_throttle(self):
        from libs.llm_client.providers import invoke_with_retry

        model = AsyncMock()
        model.ainvoke.side_effect = [
            Exception("ThrottlingException: too many requests"),
            "success",
        ]

        with patch("libs.llm_client.providers.asyncio.sleep", new_callable=AsyncMock):
            result = await invoke_with_retry(model, ["msg"], max_retries=3)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_raises_non_retryable(self):
        from libs.llm_client.providers import invoke_with_retry

        model = AsyncMock()
        model.ainvoke.side_effect = ValueError("bad input")

        with pytest.raises(ValueError):
            await invoke_with_retry(model, ["msg"], max_retries=3)

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        from libs.llm_client.providers import invoke_with_retry
        from urllib3.exceptions import ConnectTimeoutError

        model = AsyncMock()
        model.ainvoke.side_effect = ConnectTimeoutError("timeout")

        with patch("libs.llm_client.providers.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ConnectTimeoutError):
                await invoke_with_retry(model, ["msg"], max_retries=2)
        assert model.ainvoke.call_count == 2


class TestInvokeWithFallback:

    @pytest.mark.asyncio
    async def test_bedrock_success_no_fallback(self):
        from libs.llm_client.providers import invoke_with_fallback

        model = AsyncMock()
        model.ainvoke.return_value = "bedrock_result"

        with patch("libs.llm_client.providers._USE_AZURE_PRIMARY", False):
            result = await invoke_with_fallback(model, ["msg"])
        assert result == "bedrock_result"

    @pytest.mark.asyncio
    async def test_fallback_to_azure_on_bedrock_fail(self):
        from libs.llm_client.providers import invoke_with_fallback

        model = AsyncMock()
        model.ainvoke.side_effect = Exception("bedrock down")

        mock_azure = AsyncMock()
        mock_azure.ainvoke.return_value = "azure_result"

        with (
            patch("libs.llm_client.providers._USE_AZURE_PRIMARY", False),
            patch("libs.llm_client.providers.get_azure_model", return_value=mock_azure),
            patch(
                "libs.llm_client.providers.invoke_with_retry",
                side_effect=Exception("bedrock down"),
            ),
        ):
            result = await invoke_with_fallback(model, ["msg"])
        assert result == "azure_result"

    @pytest.mark.asyncio
    async def test_azure_primary_mode(self):
        from libs.llm_client.providers import invoke_with_fallback

        mock_azure = AsyncMock()
        mock_azure.ainvoke.return_value = "azure_primary"

        with (
            patch("libs.llm_client.providers._USE_AZURE_PRIMARY", True),
            patch("libs.llm_client.providers.get_azure_model", return_value=mock_azure),
        ):
            result = await invoke_with_fallback(MagicMock(), ["msg"])
        assert result == "azure_primary"


class TestGetAzureModel:

    def test_raises_without_credentials(self, monkeypatch):
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

        from libs.llm_client.providers import get_azure_model

        with pytest.raises(ValueError, match="credentials not configured"):
            get_azure_model()


class TestBedrockModelId:

    def test_default_model_id(self):
        from libs.llm_client.providers import _bedrock_model_id

        mid = _bedrock_model_id()
        assert "anthropic" in mid or "claude" in mid


# ── LLMClient tool_config tests (VT-LEO-AI-047, DI-LEO-AI-054) ───────────────


class TestLLMClientToolUse:
    """Tests for LLMClient.converse() tool_config and LLMResponse.tool_uses.
    Covers VT-047-TC-001 and TC-002 from the factory perspective.
    """

    def _make_bedrock_response(
        self, content: list, stop_reason: str = "end_turn"
    ) -> dict:
        return {
            "output": {"message": {"content": content}},
            "usage": {"inputTokens": 20, "outputTokens": 10},
            "stopReason": stop_reason,
        }

    def test_converse_without_tool_config_no_tool_config_kwarg(self):
        """Backward compat: converse() without tool_config works as before.
        converse_with_retry is imported inside _converse_bedrock, so patch via bedrock_retry.
        """
        from libs.llm_client.factory import LLMClient

        with (
            patch("libs.llm_client.bedrock_retry.converse_with_retry") as mock_retry,
            patch.object(LLMClient, "_init_bedrock", return_value=MagicMock()),
        ):
            mock_retry.return_value = self._make_bedrock_response([{"text": "verdict"}])
            client = LLMClient(provider="aws", model_id="test-model")
            resp = client.converse(
                system="s", messages=[{"role": "user", "content": "t"}]
            )

        _, kwargs = mock_retry.call_args
        assert "toolConfig" not in kwargs
        assert resp.text == "verdict"
        assert resp.tool_uses == []

    def test_converse_with_tool_config_passes_tool_config_kwarg(self):
        """converse() with tool_config passes toolConfig to Bedrock."""
        from libs.llm_client.factory import LLMClient

        tool_config = {"tools": [{"toolSpec": {"name": "test_tool"}}]}

        with (
            patch("libs.llm_client.bedrock_retry.converse_with_retry") as mock_retry,
            patch.object(LLMClient, "_init_bedrock", return_value=MagicMock()),
        ):
            mock_retry.return_value = self._make_bedrock_response([{"text": "ok"}])
            client = LLMClient(provider="aws", model_id="test-model")
            resp = client.converse(
                system="s",
                messages=[{"role": "user", "content": "t"}],
                tool_config=tool_config,
            )

        _, kwargs = mock_retry.call_args
        assert kwargs.get("toolConfig") == tool_config

    def test_converse_parses_tool_use_response_blocks(self):
        """LLMResponse.tool_uses populated when Bedrock returns toolUse blocks."""
        from libs.llm_client.factory import LLMClient

        tool_use_block = {
            "toolUse": {
                "name": "resolve_term",
                "toolUseId": "abc-123",
                "input": {"text": "Colposcopy biopsy", "label": "procedure"},
            }
        }

        with (
            patch("libs.llm_client.bedrock_retry.converse_with_retry") as mock_retry,
            patch.object(LLMClient, "_init_bedrock", return_value=MagicMock()),
        ):
            mock_retry.return_value = self._make_bedrock_response(
                [tool_use_block], stop_reason="tool_use"
            )
            client = LLMClient(provider="aws", model_id="test-model")
            resp = client.converse(
                system="s",
                messages=[{"role": "user", "content": "t"}],
                tool_config={"tools": []},
            )

        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_uses) == 1
        assert resp.tool_uses[0]["name"] == "resolve_term"
        assert resp.tool_uses[0]["toolUseId"] == "abc-123"

    def test_converse_parses_mixed_text_and_tool_use_blocks(self):
        """LLMResponse collects both text and tool_use content blocks."""
        from libs.llm_client.factory import LLMClient

        with (
            patch("libs.llm_client.bedrock_retry.converse_with_retry") as mock_retry,
            patch.object(LLMClient, "_init_bedrock", return_value=MagicMock()),
        ):
            mock_retry.return_value = self._make_bedrock_response(
                [
                    {"text": "Thinking about this..."},
                    {
                        "toolUse": {
                            "name": "get_descendants",
                            "toolUseId": "xyz-789",
                            "input": {"concept_id": "392003006", "depth": 2},
                        }
                    },
                ],
                stop_reason="tool_use",
            )
            client = LLMClient(provider="aws", model_id="test-model")
            resp = client.converse(
                system="s",
                messages=[{"role": "user", "content": "t"}],
                tool_config={"tools": []},
            )

        assert resp.text == "Thinking about this..."
        assert len(resp.tool_uses) == 1
        assert resp.tool_uses[0]["name"] == "get_descendants"

    def test_llm_response_tool_uses_defaults_to_empty_list(self):
        """LLMResponse.tool_uses defaults to [] when not provided."""
        from libs.llm_client.factory import LLMResponse

        resp = LLMResponse(
            text="hello",
            input_tokens=10,
            output_tokens=5,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="test-model",
        )
        assert resp.tool_uses == []

    def test_converse_reads_cache_read_input_tokens_key(self):
        """cached_input_tokens is parsed from canonical Bedrock usage key."""
        from libs.llm_client.factory import LLMClient

        with (
            patch("libs.llm_client.bedrock_retry.converse_with_retry") as mock_retry,
            patch.object(LLMClient, "_init_bedrock", return_value=MagicMock()),
        ):
            mock_retry.return_value = {
                "output": {"message": {"content": [{"text": "ok"}]}},
                "usage": {
                    "inputTokens": 20,
                    "outputTokens": 10,
                    "cacheReadInputTokens": 7,
                },
                "stopReason": "end_turn",
            }
            client = LLMClient(provider="aws", model_id="test-model")
            resp = client.converse(
                system="s", messages=[{"role": "user", "content": "t"}]
            )

        assert resp.cached_input_tokens == 7
