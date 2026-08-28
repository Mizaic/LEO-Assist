"""VT-LEO-AI-513 TC-007/TC-008: invoke_with_fallback fires
``track_llm_usage`` exactly once for the provider that actually
answered (Bedrock primary OR Azure fallback).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from libs.llm_client import providers, token_tracker


@pytest.fixture(autouse=True)
def _bedrock_model_env(monkeypatch):
    """Name a Bedrock model so the tests do not read a developer's .env.

    ``invoke_with_fallback`` resolves ``_bedrock_model_id()`` for the
    telemetry payload and raises when neither AWS_BEDROCK_MODEL nor
    AWS_BIG_MODEL is set. These tests used to inherit the value from a
    repo ``.env`` that a different test module leaked into os.environ,
    so they passed locally and would fail on a clean checkout.
    """
    monkeypatch.setenv("AWS_BEDROCK_MODEL", "anthropic.claude-test-model")


@pytest.fixture
def captured_callback(monkeypatch):
    captured: list[dict[str, Any]] = []

    def _cb(**kwargs):
        captured.append(kwargs)

    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_cb)
    yield captured
    token_tracker.set_tracking_callback(previous)


class _FakeLangchainResponse:
    """Mimics the surface invoked by extract_token_counts."""

    def __init__(
        self,
        input_tokens: int,
        output_tokens: int,
        provider: str,
        cache_read: int = 0,
    ) -> None:
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        if provider == "bedrock":
            self.response_metadata = {
                "usage": {
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": 0,
                }
            }
        else:
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens_details": {"cached_tokens": cache_read},
                    "completion_tokens_details": None,
                }
            }


class _PrimaryBedrock:
    """Stand-in for a langchain ChatBedrockConverse model."""

    def __init__(self, response: _FakeLangchainResponse | None, exc: Exception | None):
        self._response = response
        self._exc = exc

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages, _config=None):
        if self._exc is not None:
            raise self._exc
        return self._response


# ----- TC-007: primary path fires exactly one event ---------------------


def test_invoke_with_fallback_primary_path_fires_once(captured_callback, monkeypatch):
    monkeypatch.setattr(providers, "_USE_AZURE_PRIMARY", False)
    response = _FakeLangchainResponse(
        input_tokens=80, output_tokens=20, provider="bedrock", cache_read=5
    )
    primary = _PrimaryBedrock(response=response, exc=None)

    async def _fake_retry(model, messages, config, max_retries=5):
        return await model.ainvoke(messages, config)

    monkeypatch.setattr(providers, "invoke_with_retry", _fake_retry)

    out = asyncio.run(
        providers.invoke_with_fallback(
            primary,
            messages=[{"role": "user", "content": "hi"}],
            agent_task="vt-513-tc-007",
            patient_id="pat-7",
        )
    )

    assert out is response
    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["model_provider"] == "bedrock"
    assert payload["input_tokens"] == 80
    assert payload["output_tokens"] == 20
    assert payload["cache_read_input_tokens"] == 5
    assert payload["agent_task"] == "vt-513-tc-007"
    assert payload["patient_id"] == "pat-7"
    assert payload["success"] is True


# ----- TC-008: Bedrock fails, Azure fallback fires once with provider=azure


def test_invoke_with_fallback_falls_back_to_azure(captured_callback, monkeypatch):
    monkeypatch.setattr(providers, "_USE_AZURE_PRIMARY", False)
    bedrock_exc = RuntimeError("bedrock-down")
    primary = _PrimaryBedrock(response=None, exc=bedrock_exc)

    async def _fake_retry(model, messages, config, max_retries=5):
        return await model.ainvoke(messages, config)

    monkeypatch.setattr(providers, "invoke_with_retry", _fake_retry)

    azure_response = _FakeLangchainResponse(
        input_tokens=300, output_tokens=40, provider="azure"
    )

    class _Azure:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages, _config=None):
            return azure_response

    monkeypatch.setattr(providers, "get_azure_model", lambda: _Azure())

    out = asyncio.run(
        providers.invoke_with_fallback(
            primary,
            messages=[{"role": "user", "content": "hi"}],
            agent_task="vt-513-tc-008",
            patient_id="pat-8",
        )
    )

    assert out is azure_response
    # Two events: (1) Bedrock failure, (2) Azure success.
    assert len(captured_callback) == 2
    bedrock_event, azure_event = captured_callback
    assert bedrock_event["model_provider"] == "bedrock"
    assert bedrock_event["success"] is False
    assert "bedrock-down" in bedrock_event["error_message"]
    assert azure_event["model_provider"] == "azure"
    assert azure_event["success"] is True
    assert azure_event["input_tokens"] == 300
    assert azure_event["output_tokens"] == 40


# ----- Bonus: Azure-primary mode fires exactly one event ----------------


def test_use_azure_primary_fires_one_azure_event(captured_callback, monkeypatch):
    monkeypatch.setattr(providers, "_USE_AZURE_PRIMARY", True)
    azure_response = _FakeLangchainResponse(
        input_tokens=42, output_tokens=7, provider="azure"
    )

    class _Azure:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages, _config=None):
            return azure_response

    monkeypatch.setattr(providers, "get_azure_model", lambda: _Azure())

    out = asyncio.run(
        providers.invoke_with_fallback(
            None,
            messages=[{"role": "user", "content": "hi"}],
            agent_task="vt-513-azure-primary",
        )
    )

    assert out is azure_response
    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["model_provider"] == "azure"
    assert payload["input_tokens"] == 42
    assert payload["output_tokens"] == 7
    assert payload["success"] is True
