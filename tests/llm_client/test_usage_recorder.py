"""VT-LEO-AI-508 TC-003/TC-004: LLMUsageRecorder accumulates per-run
usage and is isolated across concurrent asyncio tasks via contextvars.
"""

from __future__ import annotations

import asyncio

import pytest

from libs.llm_client import json_helper, token_tracker
from libs.llm_client.usage_recorder import (
    LLMUsageRecorder,
    _default_tracking_callback,
    get_active_recorder,
)
from libs.llm_usage import LLMCostConfig


@pytest.fixture(autouse=True)
def _restore_default_callback():
    """Make sure the recorder's own callback is the active one for these
    tests, regardless of test ordering."""
    previous = token_tracker._tracking_callback
    token_tracker.set_tracking_callback(_default_tracking_callback)
    yield
    token_tracker.set_tracking_callback(previous)


class _FakeResponse:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.content = '{"ok": true}'
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        self.response_metadata = {"usage": {}}


@pytest.fixture
def stub_bedrock(monkeypatch):
    holder = {"responses": []}

    async def _fake_get_model():
        return object()

    async def _fake_invoke(model, messages, config=None, **_kw):
        return holder["responses"].pop(0)

    monkeypatch.setattr(json_helper, "get_bedrock_model", _fake_get_model)
    monkeypatch.setattr(json_helper, "invoke_with_retry", _fake_invoke)
    return holder


def test_recorder_accumulates_two_nested_invocations(stub_bedrock):
    stub_bedrock["responses"] = [
        _FakeResponse(100, 25),
        _FakeResponse(40, 10),
    ]

    async def _go():
        with LLMUsageRecorder() as rec:
            await json_helper.invoke_llm_json("s", "u", agent_task="a")
            await json_helper.invoke_llm_json("s", "u", agent_task="b")
            return rec

        return None  # unreachable

    rec = asyncio.run(_go())
    assert rec.usage.input_tokens == 140
    assert rec.usage.output_tokens == 35
    assert rec.usage.llm_calls == 2
    assert len(rec.calls) == 2
    assert {c.agent_task for c in rec.calls} == {"a", "b"}
    assert rec.cost_usd(LLMCostConfig.for_tier("small")) > 0


def test_concurrent_tasks_have_isolated_recorders(stub_bedrock):
    stub_bedrock["responses"] = [
        _FakeResponse(100, 10),
        _FakeResponse(100, 10),
        _FakeResponse(100, 10),
        _FakeResponse(100, 10),
    ]

    async def _scope(num_calls: int):
        with LLMUsageRecorder() as rec:
            for _ in range(num_calls):
                await json_helper.invoke_llm_json("s", "u", agent_task="x")
            return rec.usage.llm_calls

    async def _main():
        a, b = await asyncio.gather(_scope(1), _scope(3))
        return a, b

    a, b = asyncio.run(_main())
    assert a == 1
    assert b == 3


def test_outer_recorder_is_not_active_outside_with_block():
    rec = LLMUsageRecorder()
    assert get_active_recorder() is None
    with rec:
        assert get_active_recorder() is rec
    assert get_active_recorder() is None


def test_to_audit_dict_returns_uiwire_compatible_shape(stub_bedrock):
    stub_bedrock["responses"] = [_FakeResponse(50, 5)]

    async def _go():
        with LLMUsageRecorder() as rec:
            await json_helper.invoke_llm_json("s", "u", agent_task="a")
            return rec.to_audit_dict(LLMCostConfig.for_tier("small"))

    payload = asyncio.run(_go())

    for key in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "total_tokens",
        "llm_calls",
        "total_latency_ms",
        "model_name",
        "model_provider",
        "cost_usd",
    ):
        assert key in payload, f"missing {key}"
    assert payload["input_tokens"] == 50
    assert payload["output_tokens"] == 5
    assert payload["llm_calls"] == 1
    assert payload["cost_usd"] > 0
