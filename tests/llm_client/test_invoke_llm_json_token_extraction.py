"""VT-LEO-AI-508 TC-001/TC-002: invoke_llm_json fires the tracking
callback with input/output/cache token counts and latency for every
LLM call -- and still fires it (with zero token counts but non-empty
model_name + provider) when usage_metadata is missing.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from libs.llm_client import json_helper, token_tracker


class _FakeResponse:
    def __init__(
        self,
        content: str,
        usage_metadata: dict | None = None,
        cache_read: int = 0,
        cache_creation: int = 0,
    ) -> None:
        self.content = content
        if usage_metadata is not None:
            self.usage_metadata = usage_metadata
        self.response_metadata = {
            "usage": {
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            }
        }


@pytest.fixture
def captured_callback(monkeypatch):
    """Replace the global tracking callback and capture the last call."""
    captured: list[dict[str, Any]] = []

    def _cb(**kwargs):
        captured.append(kwargs)

    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_cb)
    yield captured
    token_tracker.set_tracking_callback(previous)


@pytest.fixture
def stub_bedrock(monkeypatch):
    """Replace the Bedrock model fetch + invoker with a stub the test
    controls; returns the response object for the test to swap in."""
    holder: dict[str, Any] = {"response": None}

    async def _fake_get_model():
        return object()

    async def _fake_invoke(model, messages, config=None, **_kw):
        return holder["response"]

    monkeypatch.setattr(json_helper, "get_bedrock_model", _fake_get_model)
    monkeypatch.setattr(json_helper, "invoke_with_retry", _fake_invoke)
    return holder


def test_extracts_bedrock_usage_metadata_and_forwards_tokens(
    stub_bedrock, captured_callback
):
    stub_bedrock["response"] = _FakeResponse(
        content='{"ok": true}',
        usage_metadata={"input_tokens": 120, "output_tokens": 30},
        cache_read=50,
        cache_creation=10,
    )

    result = asyncio.run(
        json_helper.invoke_llm_json(
            system_prompt="sys",
            user_message="usr",
            agent_task="vt-508-tc-001",
            patient_id="pat-1",
        )
    )

    assert result == {"ok": True}
    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["agent_task"] == "vt-508-tc-001"
    assert payload["patient_id"] == "pat-1"
    assert payload["model_provider"] == "bedrock"
    assert payload["model_name"]
    assert payload["input_tokens"] == 120
    assert payload["output_tokens"] == 30
    assert payload["cache_read_input_tokens"] == 50
    assert payload["cache_creation_input_tokens"] == 10
    assert payload["latency_ms"] >= 0
    assert payload["success"] is True


def test_callback_still_fires_when_usage_metadata_missing(
    stub_bedrock, captured_callback
):
    stub_bedrock["response"] = _FakeResponse(content='{"ok": true}')

    result = asyncio.run(
        json_helper.invoke_llm_json(
            system_prompt="sys", user_message="usr", agent_task="vt-508-tc-002"
        )
    )

    assert result == {"ok": True}
    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["input_tokens"] == 0
    assert payload["output_tokens"] == 0
    assert payload["model_name"]
    assert payload["model_provider"] == "bedrock"


def test_callback_fires_on_invocation_error_with_failure_metadata(
    stub_bedrock, captured_callback, monkeypatch
):
    async def _boom(*_a, **_kw):
        raise RuntimeError("bedrock-down")

    monkeypatch.setattr(json_helper, "invoke_with_retry", _boom)

    result = asyncio.run(
        json_helper.invoke_llm_json(
            system_prompt="sys", user_message="usr", agent_task="vt-508-tc-002b"
        )
    )

    assert "error" in result
    assert len(captured_callback) == 1
    payload = captured_callback[0]
    assert payload["success"] is False
    assert payload["error_message"]
    assert payload["model_provider"] == "bedrock"
