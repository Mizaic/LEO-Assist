"""VT-LEO-AI-508 TC-001/TC-002: invoke_llm_json fires the tracking
callback with input/output/cache token counts and latency for every
LLM call -- and still fires it (with zero token counts but non-empty
model_name + provider) when usage_metadata is missing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from libs.llm_client import json_helper, token_tracker


@dataclass
class _FakeLLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    model_id: str = "gpt-test"


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
def stub_create_llm(monkeypatch):
    """Replace create_llm with a stub client whose converse returns a preset."""
    from libs.llm_client.factory import _fire_converse_tracking

    holder: dict[str, Any] = {"response": None, "error": None}

    class _FakeClient:
        model_id = "gpt-test"

        def converse(self, **kwargs):
            if holder["error"] is not None:
                _fire_converse_tracking(
                    agent_task=kwargs.get("agent_task", "unknown"),
                    patient_id=kwargs.get("patient_id", ""),
                    model_name=self.model_id,
                    model_provider="azure",
                    input_tokens=0,
                    output_tokens=0,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                    latency_ms=0,
                    success=False,
                    error_message=str(holder["error"]),
                )
                raise holder["error"]
            resp = holder["response"]
            _fire_converse_tracking(
                agent_task=kwargs.get("agent_task", "unknown"),
                patient_id=kwargs.get("patient_id", ""),
                model_name=self.model_id,
                model_provider="azure",
                input_tokens=int(getattr(resp, "input_tokens", 0) or 0),
                output_tokens=int(getattr(resp, "output_tokens", 0) or 0),
                cache_read_input_tokens=int(
                    getattr(resp, "cached_input_tokens", 0) or 0
                ),
                cache_creation_input_tokens=int(
                    getattr(resp, "cache_creation_input_tokens", 0) or 0
                ),
                latency_ms=0,
                success=True,
            )
            return resp

    def _fake_create_llm(*_args, **_kwargs):
        return _FakeClient()

    monkeypatch.setattr(json_helper, "create_llm", _fake_create_llm)
    return holder


def test_extracts_azure_usage_and_forwards_tokens(
    stub_create_llm, captured_callback, monkeypatch
):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    stub_create_llm["response"] = _FakeLLMResponse(
        text='{"ok": true}',
        input_tokens=120,
        output_tokens=30,
        cached_input_tokens=50,
        cache_creation_input_tokens=10,
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
    assert payload["model_provider"] == "azure"
    assert payload["model_name"] == "gpt-test"
    assert payload["input_tokens"] == 120
    assert payload["output_tokens"] == 30
    assert payload["cache_read_input_tokens"] == 50
    assert payload["cache_creation_input_tokens"] == 10
    assert payload["latency_ms"] >= 0
    assert payload["success"] is True


def test_callback_still_fires_when_token_counts_zero(
    stub_create_llm, captured_callback, monkeypatch
):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    stub_create_llm["response"] = _FakeLLMResponse(text='{"ok": true}')

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
    assert payload["model_name"] == "gpt-test"
    assert payload["model_provider"] == "azure"


def test_callback_fires_on_invocation_error_with_failure_metadata(
    stub_create_llm, captured_callback, monkeypatch
):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    stub_create_llm["error"] = RuntimeError("azure-down")

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
    assert payload["model_provider"] == "azure"
