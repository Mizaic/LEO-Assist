"""VT-LEO-AI-513 TC-001..TC-006: LLMClient.converse fires
``track_llm_usage`` with the right token counts on success and
``success=False`` on failure, supports the ``agent_task`` /
``patient_id`` kwargs, isolates callback exceptions from the caller,
and feeds an active LLMUsageRecorder when one is registered.
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.llm_client import factory, token_tracker
from libs.llm_client.usage_recorder import (
    LLMUsageRecorder,
    _default_tracking_callback,
)


@pytest.fixture
def captured_callback(monkeypatch):
    """Replace the global tracking callback and capture every fire."""
    captured: list[dict[str, Any]] = []

    def _cb(**kwargs):
        captured.append(kwargs)

    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_cb)
    yield captured
    token_tracker.set_tracking_callback(previous)


# ----- Bedrock stubs ----------------------------------------------------


def _bedrock_response(
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
):
    return {
        "output": {
            "message": {"content": [{"text": '{"ok": true}'}]},
        },
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "cacheReadInputTokens": cache_read,
            "cacheWriteInputTokens": cache_write,
        },
    }


@pytest.fixture
def stub_bedrock(monkeypatch):
    """Replace converse_with_retry so no real Bedrock client is needed."""
    holder: dict[str, Any] = {"response": None, "raise": None}

    def _fake_converse(client, **kwargs):
        if holder["raise"] is not None:
            raise holder["raise"]
        return holder["response"]

    monkeypatch.setattr(
        "libs.llm_client.bedrock_retry.converse_with_retry",
        _fake_converse,
    )

    def _fake_get_client(self):
        return object()

    monkeypatch.setattr(factory.LLMClient, "_get_client", _fake_get_client)
    return holder


def _make_bedrock_client() -> factory.LLMClient:
    return factory.LLMClient(
        provider="aws",
        model_id="eu.anthropic.claude-haiku-test-v1:0",
        tier="small",
    )


# ----- Azure stubs ------------------------------------------------------


class _FakeAzureChoice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = type("M", (), {"content": content})
        self.finish_reason = finish_reason


class _FakeAzurePromptDetails:
    def __init__(self, cached_tokens: int) -> None:
        self.cached_tokens = cached_tokens


class _FakeAzureUsage:
    def __init__(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = _FakeAzurePromptDetails(cached_tokens)
        self.completion_tokens_details = None


class _FakeAzureResponse:
    def __init__(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
    ) -> None:
        self.choices = [_FakeAzureChoice('{"ok": true}')]
        self.usage = _FakeAzureUsage(prompt_tokens, completion_tokens, cached_tokens)


class _FakeAzureClient:
    def __init__(self, response: _FakeAzureResponse | None, exc: Exception | None):
        self._response = response
        self._exc = exc

        outer = self

        class _Completions:
            def create(self, **_kwargs):
                if outer._exc is not None:
                    raise outer._exc
                return outer._response

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


@pytest.fixture
def stub_azure(monkeypatch):
    holder: dict[str, Any] = {"response": None, "raise": None}
    monkeypatch.setenv("AZURE_OPENAI_TRANSPORT", "chat_completions")

    def _fake_get_client(self):
        return _FakeAzureClient(holder["response"], holder["raise"])

    monkeypatch.setattr(factory.LLMClient, "_get_client", _fake_get_client)
    return holder


def _make_azure_client() -> factory.LLMClient:
    return factory.LLMClient(
        provider="azure",
        model_id="gpt-5-mini",
        tier="small",
    )


# ----- TC-001: Bedrock success ------------------------------------------


def test_bedrock_converse_fires_tracking_with_matching_tokens(
    stub_bedrock, captured_callback
):
    stub_bedrock["response"] = _bedrock_response(
        input_tokens=120, output_tokens=30, cache_read=50, cache_write=15
    )
    client = _make_bedrock_client()

    response = client.converse(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        agent_task="vt-513-tc-001",
        patient_id="pat-1",
    )

    assert response.input_tokens == 120
    assert response.output_tokens == 30
    assert response.cached_input_tokens == 50
    assert response.cache_creation_input_tokens == 15

    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["agent_task"] == "vt-513-tc-001"
    assert payload["patient_id"] == "pat-1"
    assert payload["model_provider"] == "aws"
    assert payload["model_name"] == "eu.anthropic.claude-haiku-test-v1:0"
    assert payload["input_tokens"] == 120
    assert payload["output_tokens"] == 30
    assert payload["cache_read_input_tokens"] == 50
    assert payload["cache_creation_input_tokens"] == 15
    assert payload["model_tier"] == "small"
    assert payload["input_excludes_cache"] is True
    assert payload["latency_ms"] >= 0
    assert payload["success"] is True


# ----- TC-002: Azure success --------------------------------------------


def test_azure_converse_fires_tracking_with_matching_tokens(
    stub_azure, captured_callback
):
    stub_azure["response"] = _FakeAzureResponse(
        prompt_tokens=200, completion_tokens=80, cached_tokens=15
    )
    client = _make_azure_client()

    response = client.converse(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        agent_task="vt-513-tc-002",
        patient_id="pat-2",
    )

    assert response.input_tokens == 200
    assert response.output_tokens == 80
    assert response.cached_input_tokens == 15

    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["model_provider"] == "azure"
    assert payload["input_tokens"] == 200
    assert payload["output_tokens"] == 80
    assert payload["cache_read_input_tokens"] == 15
    assert payload["model_tier"] == "small"
    assert payload["success"] is True


# ----- TC-003: Failure path still emits, then re-raises -----------------


def test_failure_path_emits_callback_then_reraises(stub_bedrock, captured_callback):
    stub_bedrock["raise"] = RuntimeError("boom")
    client = _make_bedrock_client()

    with pytest.raises(RuntimeError, match="boom"):
        client.converse(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            agent_task="vt-513-tc-003",
        )

    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["success"] is False
    assert "boom" in payload["error_message"]
    assert payload["input_tokens"] == 0
    assert payload["output_tokens"] == 0
    assert payload["model_provider"] == "aws"


# ----- TC-004: Callback exception isolation ------------------------------


def test_callback_exception_does_not_break_converse(stub_bedrock, monkeypatch):
    stub_bedrock["response"] = _bedrock_response(input_tokens=10, output_tokens=5)

    def _bad_cb(**_kwargs):
        raise ValueError("callback exploded")

    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_bad_cb)
    try:
        client = _make_bedrock_client()
        response = client.converse(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert response.text == '{"ok": true}'
        assert response.input_tokens == 10
    finally:
        token_tracker.set_tracking_callback(previous)


# ----- TC-005: agent_task / patient_id forwarding -----------------------


def test_agent_task_and_patient_id_are_forwarded(stub_bedrock, captured_callback):
    stub_bedrock["response"] = _bedrock_response(input_tokens=1, output_tokens=1)
    client = _make_bedrock_client()

    client.converse(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        agent_task="ask_leo_smart",
        patient_id="9437821",
    )

    payload = captured_callback[0]
    assert payload["agent_task"] == "ask_leo_smart"
    assert payload["patient_id"] == "9437821"


# ----- TC-006: Active LLMUsageRecorder picks up sync calls --------------


def test_active_recorder_accumulates_two_converse_calls(stub_bedrock, monkeypatch):
    """Wrap two stubbed Bedrock calls in an LLMUsageRecorder; the
    default recorder callback must accumulate input/output/calls
    without any caller change."""
    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_default_tracking_callback)
    try:
        client = _make_bedrock_client()
        with LLMUsageRecorder() as rec:
            stub_bedrock["response"] = _bedrock_response(
                input_tokens=10, output_tokens=5
            )
            client.converse(system="sys", messages=[{"role": "user", "content": "1"}])
            stub_bedrock["response"] = _bedrock_response(
                input_tokens=20, output_tokens=8
            )
            client.converse(system="sys", messages=[{"role": "user", "content": "2"}])
    finally:
        token_tracker.set_tracking_callback(previous)

    assert rec.usage.input_tokens == 30
    assert rec.usage.output_tokens == 13
    assert rec.usage.llm_calls == 2
    assert len(rec.calls) == 2
