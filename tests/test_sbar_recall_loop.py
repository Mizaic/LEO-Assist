"""SBAR bounded recall LLM tool loop tests (Gate 3 E3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from libs.sbar.recall_loop import run_recall_loop
from libs.sbar.recall_preflight import RecallBudget
from libs.sbar.recall_tools import RecallScope, RecallToolRegistry


@dataclass
class _FakeLlmResponse:
    text: str = ""
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    raw_output_items: list[dict[str, Any]] = field(default_factory=list)


def _registry(
    *,
    allowed: list[str],
    chunks: dict[str, dict[str, Any]] | None = None,
    reason: str | None = None,
    facts: list[dict[str, Any]] | None = None,
) -> RecallToolRegistry:
    scope = RecallScope(
        tenant_id="t1",
        patient_id="p1",
        referral_id="rr-1",
        run_id="run-recall-1",
        allowed_chunk_ids=frozenset(allowed),
    )

    def _find_reason() -> dict[str, Any] | None:
        if not reason:
            return None
        return {"reason_text": reason, "chunk_id": allowed[:1]}

    return RecallToolRegistry(
        scope=scope,
        list_coded_facts=lambda: list(facts or []),
        fetch_chunk=lambda cid: (chunks or {}).get(str(cid)),
        find_referral_reason=_find_reason,
    )


@pytest.mark.asyncio
async def test_structured_reason_skips_llm_loop() -> None:
    registry = _registry(allowed=["c1"], reason="Suspected lung cancer.")
    result = await run_recall_loop(
        registry=registry,
        budget=RecallBudget(max_chunk_fetches=5, max_llm_calls=2, max_tokens=1000),
        preflight_reasons=["missing_referral_reason"],
        allowed_chunk_ids=["c1"],
        run_id="run-recall-1",
    )
    assert result.evidence is not None
    assert "lung cancer" in result.evidence.reason_text.lower()
    assert result.llm_calls == 0


@pytest.mark.asyncio
async def test_llm_loop_fetches_manifest_chunk_and_submits() -> None:
    registry = _registry(
        allowed=["c1"],
        chunks={"c1": {"id": "c1", "text": "Referral for progressive dysphagia."}},
    )
    calls: dict[str, Any] = {"n": 0, "response_items": []}

    async def _fake_converse(_system, _messages, **kwargs):
        calls["n"] += 1
        calls["response_items"].append(list(kwargs.get("response_items") or []))
        if calls["n"] == 1:
            return _FakeLlmResponse(
                raw_output_items=[
                    {
                        "type": "function_call",
                        "call_id": "tu-1",
                        "name": "fetch_chunk",
                        "arguments": '{"chunk_id": "c1"}',
                    }
                ],
                tool_uses=[
                    {
                        "name": "fetch_chunk",
                        "toolUseId": "tu-1",
                        "input": {"chunk_id": "c1"},
                    }
                ]
            )
        return _FakeLlmResponse(
            raw_output_items=[
                {
                    "type": "function_call",
                    "call_id": "tu-2",
                    "name": "submit_recall_result",
                    "arguments": "{}",
                }
            ],
            tool_uses=[
                {
                    "name": "submit_recall_result",
                    "toolUseId": "tu-2",
                    "input": {
                        "reason_text": "Progressive dysphagia.",
                        "chunk_id": "c1",
                        "missing": [],
                        "complete": True,
                    },
                }
            ]
        )

    result = await run_recall_loop(
        registry=registry,
        budget=RecallBudget(max_chunk_fetches=5, max_llm_calls=2, max_tokens=1000),
        preflight_reasons=["missing_referral_reason"],
        allowed_chunk_ids=["c1"],
        run_id="run-recall-1",
        converse_fn=_fake_converse,
    )
    assert result.evidence is not None
    assert result.evidence.chunk_id == "c1"
    assert result.llm_calls == 2
    assert registry.fetch_count == 1
    continuation = calls["response_items"][1]
    assert continuation[0]["call_id"] == "tu-1"
    assert continuation[1]["type"] == "function_call_output"
    assert continuation[1]["call_id"] == "tu-1"


@pytest.mark.asyncio
async def test_out_of_manifest_fetch_does_not_spend_budget() -> None:
    registry = _registry(allowed=["c1"], chunks={"c-secret": {"id": "c-secret"}})
    await run_recall_loop(
        registry=registry,
        budget=RecallBudget(max_chunk_fetches=5, max_llm_calls=0, max_tokens=1000),
        preflight_reasons=["missing_referral_reason"],
        allowed_chunk_ids=["c1"],
        run_id="run-recall-1",
    )
    registry.fetch_chunk_scoped("c-secret")
    assert registry.fetch_count == 0


@pytest.mark.asyncio
async def test_budget_exhaustion_sets_missing_flags() -> None:
    registry = _registry(allowed=["c1", "c2", "c3"])

    async def _never_submit(_system, _messages, **_kwargs):
        return _FakeLlmResponse(
            tool_uses=[
                {
                    "name": "fetch_chunk",
                    "toolUseId": "tu-fetch",
                    "input": {"chunk_id": "c1"},
                }
            ]
        )

    result = await run_recall_loop(
        registry=registry,
        budget=RecallBudget(max_chunk_fetches=1, max_llm_calls=1, max_tokens=100),
        preflight_reasons=["missing_referral_reason"],
        allowed_chunk_ids=["c1", "c2"],
        run_id="run-recall-1",
        converse_fn=_never_submit,
    )
    assert result.evidence is None
    assert result.exhaustion is not None
    assert result.exhaustion.needs_review is True
    assert "RECALL_LLM_CALL_LIMIT" in result.exhaustion.missing_flags


@pytest.mark.asyncio
async def test_call_recall_wires_manifest_policy() -> None:
    from libs.sbar.prompt_calls import call_recall

    registry = _registry(allowed=["c1"], reason="Chest pain referral.")
    budget = RecallBudget(max_chunk_fetches=5, max_llm_calls=2, max_tokens=50000)

    def _prompt(_name: str) -> str:
        return "recall-system"

    result = await call_recall(
        registry=registry,
        budget=budget,
        preflight_reasons=["missing_referral_reason"],
        allowed_chunk_ids=["c1"],
        run_id="run-recall-2",
        prompt_fetcher=_prompt,
    )
    assert result["evidence"] is not None
    assert result["error"] is None
    assert result["llm_calls"] == 0
