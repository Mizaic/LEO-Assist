"""Single-model runner on AWS Bedrock.

Tier selection:
  CONSENSUS_AWS_TIER       -- extraction step (default "big" / Sonnet).
  CONSENSUS_VERIFIER_TIER  -- verifier step   (default: same as CONSENSUS_AWS_TIER).

Set CONSENSUS_AWS_TIER=small to use Haiku for extraction; leave
CONSENSUS_VERIFIER_TIER unset (or set to "big") to keep Sonnet for the more
demanding code-verification step. This gives the best cost/quality split.

Examples:
  CONSENSUS_AWS_TIER=small                          -- Haiku extraction + Haiku verify
  CONSENSUS_AWS_TIER=small CONSENSUS_VERIFIER_TIER=big  -- Haiku extraction + Sonnet verify

The ConsensusResult fields (aws_verdict, azure_verdict, agreed, etc.)
are kept for API compatibility with existing callers.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from libs.llm_client.factory import LLMResponse, create_llm

logger = logging.getLogger(__name__)

# Valid tier values for AWS Bedrock: "small" (Haiku), "big" (Sonnet), "max" (Opus).
_VALID_CONSENSUS_TIERS = frozenset({"small", "big", "max"})


def _consensus_aws_tier() -> str:
    """Extraction tier -- controlled by CONSENSUS_AWS_TIER (default: big)."""
    raw = (os.getenv("CONSENSUS_AWS_TIER") or "big").strip().lower()
    return raw if raw in _VALID_CONSENSUS_TIERS else "big"


def _consensus_verifier_tier() -> str:
    """Verifier tier -- CONSENSUS_VERIFIER_TIER; falls back to CONSENSUS_AWS_TIER."""
    raw = (os.getenv("CONSENSUS_VERIFIER_TIER") or "").strip().lower()
    if raw in _VALID_CONSENSUS_TIERS:
        return raw
    return _consensus_aws_tier()


@dataclass
class ConsensusResult:
    """Outcome of a dual-model consensus check."""

    verdict: Any
    confidence: float = 0.0
    reason: str = ""
    aws_verdict: Any = ""
    azure_verdict: Any = ""
    arbitrator_verdict: Any = ""
    arbitrator_model_id: str = ""
    agreed: bool = False
    single_model_fallback: bool = False  # True when only one provider succeeded (unvalidated)
    model_ids: list[str] = field(default_factory=list)
    # Aggregated token counts across ALL provider calls in this consensus run
    # (small model A + small model B + optional Sonnet arbitrator).
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    llm_calls: int = 0


def _call_provider(
    provider: str,
    tier: str,
    system_prompt: str,
    user_msg: str,
    max_tokens: int,
    *,
    json_mode: bool = False,
) -> LLMResponse:
    client = create_llm(provider=provider, tier=tier)
    return client.converse(
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.0,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )



def _sum_tokens(responses: list[LLMResponse | None]) -> dict[str, int]:
    """Sum token fields across a list of LLMResponse objects (None entries skipped)."""
    return {
        "input_tokens":        sum(r.input_tokens        for r in responses if r),
        "output_tokens":       sum(r.output_tokens       for r in responses if r),
        "cached_input_tokens": sum(r.cached_input_tokens for r in responses if r),
        "llm_calls":           sum(1                     for r in responses if r),
    }


def run_consensus(
    *,
    system_prompt: str,
    user_msg: str,
    parse_fn: Callable[[str], Any],
    fail_verdict: Any,
    max_tokens: int = 150,
    json_mode: bool = False,
    tier: str | None = None,
) -> ConsensusResult:
    """Call AWS Bedrock once at the specified tier (default: ``CONSENSUS_AWS_TIER``).

    Callers that run the verifier step should pass ``tier=_consensus_verifier_tier()``
    so the verifier can be pinned to a stronger model independently of the extraction tier.

    Args:
        system_prompt: System prompt for the model.
        user_msg: User message (typically JSON-serialised context).
        parse_fn: Extracts the verdict from raw LLM response text.
                  Must return a falsy value on parse failure.
        fail_verdict: Returned when the call fails or parse fails after retry.
        max_tokens: Max output tokens for the call.
        json_mode: Passed through to the provider client.
        tier: AWS tier override ("small", "big", "max"). Defaults to CONSENSUS_AWS_TIER.

    Returns:
        ConsensusResult with the verdict and token totals.
    """
    if tier is None or tier not in _VALID_CONSENSUS_TIERS:
        tier = _consensus_aws_tier()
    label = f"aws/{tier}"
    resp: LLMResponse | None = None
    verdict: Any = None
    model_id = ""

    try:
        resp = _call_provider(
            "aws", tier, system_prompt, user_msg, max_tokens, json_mode=json_mode
        )
        verdict = parse_fn(resp.text)
        model_id = resp.model_id
    except Exception:
        logger.warning("Consensus (%s): call failed", label, exc_info=True)

    # One parse-retry on empty/unparseable output
    if resp and not verdict:
        logger.warning(
            "Consensus (%s): parse failed (stop_reason=%r text_len=%d) -- retrying",
            label,
            resp.stop_reason,
            len(resp.text or ""),
        )
        try:
            retry_msg = (
                user_msg
                + "\n\nSTRICT OUTPUT REMINDER: Return ONLY one valid JSON object. "
                + "No prose, no markdown fences, no explanation."
            )
            resp_retry = _call_provider(
                "aws", tier, system_prompt, retry_msg, max_tokens, json_mode=json_mode
            )
            verdict = parse_fn(resp_retry.text)
            if verdict:
                resp = resp_retry
                model_id = resp_retry.model_id
                logger.info("Consensus (%s): parse-retry recovered.", label)
        except Exception:
            logger.warning("Consensus (%s): parse-retry failed", label, exc_info=True)

    tok = _sum_tokens([resp])
    if not verdict:
        logger.error("Consensus (%s): failed after retry -- returning fail_verdict", label)
        return ConsensusResult(
            verdict=fail_verdict,
            reason=f"{label} call/parse failed",
            model_ids=[model_id] if model_id else [],
            input_tokens=tok["input_tokens"],
            output_tokens=tok["output_tokens"],
            cached_input_tokens=tok["cached_input_tokens"],
            llm_calls=tok["llm_calls"],
        )

    logger.info("Consensus (%s): verdict=%s", label, verdict)
    return ConsensusResult(
        verdict=verdict,
        aws_verdict=verdict,
        agreed=True,
        model_ids=[model_id] if model_id else [],
        input_tokens=tok["input_tokens"],
        output_tokens=tok["output_tokens"],
        cached_input_tokens=tok["cached_input_tokens"],
        llm_calls=tok["llm_calls"],
    )
