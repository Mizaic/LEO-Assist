"""Bounded SBAR recall LLM tool loop (Gate 3 E3.1-E3.3).

Atlas trace:
  DO: DO-8CD63B3B
  DI: DI-CC00ABBD
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8CD63B3B")
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from libs.llm_client.factory import create_llm
from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.prompts.sbar_recall_v1 import SBAR_RECALL_SYSTEM_V1, build_recall_tool_config
from libs.sbar.recall_preflight import (
    RecallBudget,
    RecallExhaustionResult,
    check_recall_budget,
)
from libs.sbar.recall_tools import RecallToolRegistry
from libs.sbar.situation_source import ReferralReasonEvidence

logger = logging.getLogger(__name__)

ConverseFn = Callable[..., Awaitable[Any]]


@dataclass
class RecallLoopResult:
    evidence: ReferralReasonEvidence | None = None
    exhaustion: RecallExhaustionResult | None = None
    missing: list[str] = field(default_factory=list)
    llm_calls: int = 0
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _serialise_recall_context(
    *,
    preflight_reasons: list[str],
    allowed_chunk_ids: list[str],
) -> str:
    body = {
        "preflight_reasons": list(preflight_reasons or []),
        "allowed_chunk_ids": list(allowed_chunk_ids or []),
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _tool_result_block(tool_use_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"json": payload}],
        }
    }


def _dispatch_tool(
    registry: RecallToolRegistry, name: str, inp: dict[str, Any]
) -> dict[str, Any]:
    if name == "list_coded_facts":
        facts = registry.list_coded_facts_scoped()
        return {"facts": facts, "count": len(facts)}
    if name == "fetch_chunk":
        chunk_id = str(inp.get("chunk_id") or "").strip()
        chunk = registry.fetch_chunk_scoped(chunk_id)
        if chunk is None:
            return {"found": False, "chunk_id": chunk_id}
        text = sanitise_for_prompt(str(chunk.get("text") or ""), max_chars=4000)
        return {"found": True, "chunk_id": chunk_id, "text": text}
    if name == "find_referral_reason":
        raw = registry.find_referral_reason_scoped()
        if not raw:
            return {"found": False}
        return {"found": True, **raw}
    if name == "submit_recall_result":
        return {"accepted": True, **inp}
    return {"error": f"unsupported_tool:{name}"}


def _evidence_from_submit(
    payload: dict[str, Any],
    *,
    run_id: str,
) -> ReferralReasonEvidence | None:
    reason = str(payload.get("reason_text") or "").strip()
    if not reason:
        return None
    chunk_id = str(payload.get("chunk_id") or "").strip() or None
    return ReferralReasonEvidence(
        reason_text=reason,
        source_type="RecallTool",
        source_id=chunk_id or "",
        chunk_id=chunk_id,
        evidence_text=reason,
        run_id=run_id or None,
    )


def _budget_exhaustion(
    registry: RecallToolRegistry,
    budget: RecallBudget,
    *,
    llm_calls: int,
    tokens_used: int,
    extra_missing: list[str] | None = None,
) -> RecallExhaustionResult:
    result = check_recall_budget(
        chunk_fetches=registry.fetch_count,
        llm_calls=llm_calls,
        tokens_used=tokens_used,
        budget=budget,
    )
    if extra_missing:
        merged = list(dict.fromkeys(list(result.missing_flags) + list(extra_missing)))
        result.missing_flags = merged
        result.exhausted = bool(merged)
        result.needs_review = bool(merged)
    return result


async def run_recall_loop(
    *,
    registry: RecallToolRegistry,
    budget: RecallBudget,
    preflight_reasons: list[str],
    allowed_chunk_ids: list[str],
    run_id: str,
    system_prompt: str | None = None,
    patient_id: str = "",
    provider: str = "aws",
    tier: str = "big",
    converse_fn: ConverseFn | None = None,
) -> RecallLoopResult:
    """Run deterministic tools first, then a bounded LLM tool loop."""
    audit_log = list(registry.audit_log)
    found = _try_structured_reason(registry, run_id=run_id)
    if found is not None:
        exhaustion = check_recall_budget(
            chunk_fetches=registry.fetch_count,
            llm_calls=0,
            tokens_used=0,
            budget=budget,
        )
        return RecallLoopResult(
            evidence=found,
            exhaustion=exhaustion,
            missing=[],
            llm_calls=0,
            audit_log=audit_log,
        )

    if not preflight_reasons:
        return RecallLoopResult(
            evidence=None,
            exhaustion=check_recall_budget(
                chunk_fetches=registry.fetch_count,
                llm_calls=0,
                tokens_used=0,
                budget=budget,
            ),
            missing=[],
            llm_calls=0,
            audit_log=audit_log,
        )

    system = system_prompt or SBAR_RECALL_SYSTEM_V1
    user = _serialise_recall_context(
        preflight_reasons=preflight_reasons,
        allowed_chunk_ids=allowed_chunk_ids,
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    tool_config = build_recall_tool_config()
    llm_calls = 0
    tokens_used = 0
    submit_payload: dict[str, Any] | None = None

    while llm_calls < budget.max_llm_calls:
        llm_calls += 1
        resp = await _converse(
            converse_fn,
            system=system,
            messages=messages,
            provider=provider,
            tier=tier,
            patient_id=patient_id,
            tool_config=tool_config,
        )
        tokens_used += _estimate_tokens(resp)
        tool_uses = list(getattr(resp, "tool_uses", None) or [])
        if not tool_uses:
            break

        assistant_blocks: list[dict[str, Any]] = []
        if getattr(resp, "text", None):
            assistant_blocks.append({"text": resp.text})
        assistant_blocks.extend({"toolUse": tu} for tu in tool_uses)
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            name = str(tu.get("name") or "")
            tool_use_id = str(tu.get("toolUseId") or "")
            inp = dict(tu.get("input") or {})
            payload = _dispatch_tool(registry, name, inp)
            if name == "submit_recall_result":
                submit_payload = payload
            tool_results.append(_tool_result_block(tool_use_id, payload))

        messages.append({"role": "user", "content": tool_results})
        audit_log = list(registry.audit_log)

        if submit_payload is not None:
            missing = list(submit_payload.get("missing") or [])
            evidence = _evidence_from_submit(submit_payload, run_id=run_id)
            exhaustion = _budget_exhaustion(
                registry,
                budget,
                llm_calls=llm_calls,
                tokens_used=tokens_used,
                extra_missing=missing if not evidence else None,
            )
            return RecallLoopResult(
                evidence=evidence,
                exhaustion=exhaustion,
                missing=missing,
                llm_calls=llm_calls,
                audit_log=audit_log,
                raw={"submit": submit_payload},
            )

        if registry.fetch_count >= budget.max_chunk_fetches:
            break

    missing = ["missing_referral_reason"]
    if registry.fetch_count >= budget.max_chunk_fetches:
        missing.append("RECALL_CHUNK_FETCH_LIMIT")
    if llm_calls >= budget.max_llm_calls:
        missing.append("RECALL_LLM_CALL_LIMIT")
    exhaustion = _budget_exhaustion(
        registry,
        budget,
        llm_calls=llm_calls,
        tokens_used=tokens_used,
        extra_missing=missing,
    )
    return RecallLoopResult(
        evidence=None,
        exhaustion=exhaustion,
        missing=list(dict.fromkeys(missing)),
        llm_calls=llm_calls,
        audit_log=audit_log,
    )


def _try_structured_reason(
    registry: RecallToolRegistry,
    *,
    run_id: str,
) -> ReferralReasonEvidence | None:
    raw = registry.find_referral_reason_scoped()
    if not raw or not str(raw.get("reason_text") or "").strip():
        return None
    chunk_id = str(raw.get("chunk_id") or "") or None
    reason = str(raw.get("reason_text") or "").strip()
    return ReferralReasonEvidence(
        reason_text=reason,
        source_type="RecallTool",
        source_id=chunk_id or "",
        chunk_id=chunk_id,
        evidence_text=reason,
        run_id=run_id or None,
    )


async def _converse(
    converse_fn: ConverseFn | None,
    *,
    system: str,
    messages: list[dict[str, Any]],
    provider: str,
    tier: str,
    patient_id: str,
    tool_config: dict[str, Any],
) -> Any:
    if converse_fn is not None:
        return await converse_fn(
            system,
            messages,
            tool_config=tool_config,
            agent_task="sbar_recall",
            patient_id=patient_id,
        )
    client = await asyncio.to_thread(create_llm, provider=provider, tier=tier)
    return await asyncio.to_thread(
        client.converse,
        system=system,
        messages=messages,
        max_tokens=512,
        temperature=0.0,
        tool_config=tool_config,
        agent_task="sbar_recall",
        patient_id=patient_id,
    )


def _estimate_tokens(resp: Any) -> int:
    usage = getattr(resp, "usage", None) or {}
    if isinstance(usage, dict):
        return int(usage.get("input_tokens") or 0) + int(
            usage.get("output_tokens") or 0
        )
    return 0
