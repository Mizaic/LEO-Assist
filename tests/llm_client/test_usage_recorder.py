"""VT-LEO-AI-508 TC-003/TC-004: LLMUsageRecorder accumulates per-run
usage and is isolated across concurrent asyncio tasks via contextvars.
"""

from __future__ import annotations

import asyncio

import pytest

from libs.llm_client import json_helper, token_tracker
from libs.llm_client.usage_recorder import (
    LLMCallRecord,
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


@pytest.fixture
def stub_create_llm(monkeypatch):
    from libs.llm_client.factory import _fire_converse_tracking

    holder = {"responses": [], "error": None}

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
            resp = holder["responses"].pop(0)
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


def test_recorder_accumulates_two_nested_invocations(stub_create_llm, monkeypatch):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    from libs.llm_client.factory import LLMResponse

    stub_create_llm["responses"] = [
        LLMResponse(
            text='{"ok": true}',
            input_tokens=100,
            output_tokens=25,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
        LLMResponse(
            text='{"ok": true}',
            input_tokens=40,
            output_tokens=10,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
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


def test_concurrent_tasks_have_isolated_recorders(stub_create_llm, monkeypatch):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    from libs.llm_client.factory import LLMResponse

    stub_create_llm["responses"] = [
        LLMResponse(
            text='{"ok": true}',
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
        LLMResponse(
            text='{"ok": true}',
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
        LLMResponse(
            text='{"ok": true}',
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
        LLMResponse(
            text='{"ok": true}',
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
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


def _sample_call(**overrides: object) -> LLMCallRecord:
    payload = {
        "agent_task": "sbar_background",
        "model_name": "gpt-5.4-mini",
        "model_provider": "azure",
        "input_tokens": 1000,
        "output_tokens": 40,
        "cached_input_tokens": 0,
        "latency_ms": 20,
        "success": True,
    }
    payload.update(overrides)
    return LLMCallRecord(**payload)


def test_nested_recorder_forwards_calls_to_parent():
    """Inner SBAR recorder must not hide tokens from the durable step.

    DI-9456E5BE -- spend totals under-count when SBAR opens a nested
    LLMUsageRecorder inside the step recorder (2026-09-16 Azure gap).
    """
    parent = LLMUsageRecorder()
    child = LLMUsageRecorder()
    with parent:
        with child:
            child.record(_sample_call())
    assert child.usage.llm_calls == 1
    assert parent.usage.llm_calls == 1
    assert parent.usage.input_tokens == 1000
    assert parent.usage.output_tokens == 40


def test_to_audit_dict_returns_uiwire_compatible_shape(stub_create_llm, monkeypatch):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    from libs.llm_client.factory import LLMResponse

    stub_create_llm["responses"] = [
        LLMResponse(
            text='{"ok": true}',
            input_tokens=50,
            output_tokens=5,
            cached_input_tokens=0,
            stop_reason="end_turn",
            model_id="gpt-test",
        ),
    ]

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


def test_recorder_prices_gpt54_at_big_rates_when_env_is_small(monkeypatch):
    monkeypatch.setenv("PIPELINE_MODEL_PROVIDER", "azure")
    monkeypatch.setenv("PIPELINE_MODEL_TIER", "small")
    for suffix in (
        "COST_PER_1M_INPUT_TOKEN",
        "COST_PER_1M_CACHED_INPUT_TOKEN",
        "COST_PER_1M_OUTPUT_TOKEN",
        "COST_PER_1M_CACHE_WRITE_TOKEN",
    ):
        monkeypatch.delenv(f"AZURE_OPENAI_BIG_MODEL_{suffix}", raising=False)
        monkeypatch.delenv(f"AZURE_OPENAI_SMALL_MODEL_{suffix}", raising=False)
    rec = LLMUsageRecorder()
    rec.record(
        LLMCallRecord(
            agent_task="sbar_background",
            model_name="gpt-5.4",
            model_provider="azure",
            input_tokens=22576,
            output_tokens=1104,
            cached_input_tokens=0,
            latency_ms=100,
            success=True,
        )
    )
    env_cfg = LLMCostConfig.from_env()
    assert abs(rec.cost_usd(env_cfg) - 0.073) < 1e-6
    mini_cost = rec.usage.cost_usd(env_cfg)
    assert abs(mini_cost - 0.0219) < 1e-6
