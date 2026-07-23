"""Deterministic recall preflight and exhaustion flags (E3.3).

Atlas trace:
  DO: DO-8CD63B3B
  DI: DI-CC00ABBD
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8CD63B3B")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecallBudget:
    max_chunk_fetches: int = 5
    max_llm_calls: int = 2
    max_tokens: int = 50000


@dataclass
class RecallPreflightResult:
    should_recall: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class RecallExhaustionResult:
    exhausted: bool
    missing_flags: list[str] = field(default_factory=list)
    needs_review: bool = False
    source_accounting: dict[str, Any] = field(default_factory=dict)


def preflight_recall(
    *,
    missing_slots: list[str] | None = None,
    coverage_gaps: int = 0,
    approved_conditions: tuple[str, ...] = (
        "missing_referral_reason",
        "uncoded_coverage_gap",
        "missing_priority",
    ),
) -> RecallPreflightResult:
    """Trigger recall only for approved missing-slot/coverage conditions."""
    reasons: list[str] = []
    for slot in missing_slots or []:
        if slot in approved_conditions:
            reasons.append(slot)
    if coverage_gaps > 0 and "uncoded_coverage_gap" in approved_conditions:
        reasons.append("uncoded_coverage_gap")
    return RecallPreflightResult(should_recall=bool(reasons), reasons=reasons)


def check_recall_budget(
    *,
    chunk_fetches: int,
    llm_calls: int,
    tokens_used: int,
    budget: RecallBudget,
) -> RecallExhaustionResult:
    """Return exhaustion flags when a bounded recall budget is exceeded."""
    missing: list[str] = []
    if chunk_fetches >= budget.max_chunk_fetches:
        missing.append("RECALL_CHUNK_FETCH_LIMIT")
    if llm_calls >= budget.max_llm_calls:
        missing.append("RECALL_LLM_CALL_LIMIT")
    if tokens_used >= budget.max_tokens:
        missing.append("RECALL_TOKEN_LIMIT")
    exhausted = bool(missing)
    return RecallExhaustionResult(
        exhausted=exhausted,
        missing_flags=missing,
        needs_review=exhausted,
        source_accounting={
            "chunk_fetches": chunk_fetches,
            "llm_calls": llm_calls,
            "tokens_used": tokens_used,
            "budget": {
                "maxChunkFetches": budget.max_chunk_fetches,
                "maxLlmCalls": budget.max_llm_calls,
                "maxTokens": budget.max_tokens,
            },
        },
    )


def recall_policy_from_manifest(manifest: dict[str, Any]) -> RecallBudget:
    recall = (
        manifest.get("recall")
        or manifest.get("referral_policy", {}).get("recall")
        or {}
    )
    return RecallBudget(
        max_chunk_fetches=int(recall.get("maxChunkFetches") or 5),
        max_llm_calls=int(recall.get("maxLlmCalls") or 2),
        max_tokens=int(recall.get("maxTokens") or 50000),
    )
