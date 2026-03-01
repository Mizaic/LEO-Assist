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

        with patch("libs.llm_client.providers._USE_AZURE_PRIMARY", False), \
             patch("libs.llm_client.providers.get_azure_model", return_value=mock_azure), \
             patch("libs.llm_client.providers.invoke_with_retry", side_effect=Exception("bedrock down")):
            result = await invoke_with_fallback(model, ["msg"])
        assert result == "azure_result"

    @pytest.mark.asyncio
    async def test_azure_primary_mode(self):
        from libs.llm_client.providers import invoke_with_fallback

        mock_azure = AsyncMock()
        mock_azure.ainvoke.return_value = "azure_primary"

        with patch("libs.llm_client.providers._USE_AZURE_PRIMARY", True), \
             patch("libs.llm_client.providers.get_azure_model", return_value=mock_azure):
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
