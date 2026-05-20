"""LLM-judge runner used by the disorder gate and coding-verifier steps.

Atlas trace:
  DO: DO-4AB6D361
  Also implements: DO-9CA0B5A8
  DI: DI-80DD8A47, DI-E1913514
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4AB6D361")

The pipeline is NER-then-LLM-as-judge-and-fixer: the deterministic post-
processing stack emits entity dicts and terminology candidates, then the
LLM is invoked as a *judge* to classify disorder context or validate a
terminology match.

Two execution modes
-------------------
Single model (default)
    One AWS Bedrock call at the configured tier. A second "strict reminder"
    retry is issued if the first call fails to parse. This is the production
    default because the cost/latency of the second provider rarely justifies
    the marginal accuracy gain for these short classification decisions.

Dual-model consensus (opt-in)
    Enable with ``CONSENSUS_DUAL_MODEL=true``. Runs AWS small-tier and Azure
    small-tier judges in parallel. If they agree, the shared verdict wins.
    If they disagree (or one fails), a big-tier AWS model arbitrates. This
    mirrors the design previously described in the docstring but costs 2-3x
    tokens per call.

Tier selection
--------------
``CONSENSUS_AWS_TIER`` -- AWS tier for single-model mode and the dual-model
    arbitrator (default ``small`` / Haiku). When unset, falls back to
    ``PIPELINE_MODEL_TIER`` (also ``small`` in container defaults).
``CONSENSUS_VERIFIER_TIER`` -- tier used when the caller passes the verifier
    override (``tier=_consensus_verifier_tier()``). Falls back to
    ``CONSENSUS_AWS_TIER`` if unset.
``PIPELINE_CONSENSUS_MODE`` -- when ``true``, enables dual-model mode (same as
    ``CONSENSUS_DUAL_MODEL=true``). Defaults to ``false``.

``ConsensusResult`` fields are kept for API compatibility -- in single-model
mode ``azure_verdict``, ``arbitrator_verdict``, and ``arbitrator_model_id``
remain empty but ``agreed`` is True iff the single call produced a verdict.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from libs.llm_client.factory import LLMResponse, create_llm

logger = logging.getLogger(__name__)

_VALID_CONSENSUS_TIERS = frozenset({"small", "big", "max"})


def _pipeline_model_tier() -> str:
    raw = (os.getenv("PIPELINE_MODEL_TIER") or "small").strip().lower()
    return raw if raw in _VALID_CONSENSUS_TIERS else "small"


def _consensus_aws_tier() -> str:
    raw = (os.getenv("CONSENSUS_AWS_TIER") or "").strip().lower()
    if raw in _VALID_CONSENSUS_TIERS:
        return raw
    return _pipeline_model_tier()


def _consensus_verifier_tier() -> str:
    raw = (os.getenv("CONSENSUS_VERIFIER_TIER") or "").strip().lower()
    if raw in _VALID_CONSENSUS_TIERS:
        return raw
    return _consensus_aws_tier()


def _env_flag(name: str, default: str = "false") -> bool:
    return (os.getenv(name) or default).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _dual_model_enabled() -> bool:
    """Dual-model (AWS + Azure small, big arbitrator) is opt-in only."""
    explicit = (os.getenv("CONSENSUS_DUAL_MODEL") or "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return False
    if explicit in {"1", "true", "yes", "on"}:
        return True
    return _env_flag("PIPELINE_CONSENSUS_MODE", "false")


@dataclass
class ConsensusResult:
    """Outcome of a single-model or dual-model judge call."""

    verdict: Any
    confidence: float = 0.0
    reason: str = ""
    aws_verdict: Any = ""
    azure_verdict: Any = ""
    arbitrator_verdict: Any = ""
    arbitrator_model_id: str = ""
    agreed: bool = False
    single_model_fallback: bool = False
    model_ids: list[str] = field(default_factory=list)
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
    agent_task: str = "consensus",
    patient_id: str = "",
) -> LLMResponse:
    client = create_llm(provider=provider, tier=tier)
    return client.converse(
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.0,
        max_tokens=max_tokens,
        json_mode=json_mode,
        agent_task=agent_task,
        patient_id=patient_id,
    )


def _sum_tokens(responses: list[LLMResponse | None]) -> dict[str, int]:
    return {
        "input_tokens": sum(r.input_tokens for r in responses if r),
        "output_tokens": sum(r.output_tokens for r in responses if r),
        "cached_input_tokens": sum(r.cached_input_tokens for r in responses if r),
        "llm_calls": sum(1 for r in responses if r),
    }


def _safe_call(
    provider: str,
    tier: str,
    system_prompt: str,
    user_msg: str,
    max_tokens: int,
    parse_fn: Callable[[str], Any],
    *,
    json_mode: bool = False,
) -> tuple[LLMResponse | None, Any, str]:
    """Call a single provider and return ``(response, verdict, model_id)``.

    Any provider error becomes ``(None, None, "")`` -- callers decide how to
    degrade.
    """
    try:
        resp = _call_provider(
            provider, tier, system_prompt, user_msg, max_tokens, json_mode=json_mode
        )
    except Exception:
        logger.warning("Consensus (%s/%s): call failed", provider, tier, exc_info=True)
        return None, None, ""
    verdict = parse_fn(resp.text) if resp else None
    return resp, verdict, (resp.model_id if resp else "")


def _single_model(
    system_prompt: str,
    user_msg: str,
    parse_fn: Callable[[str], Any],
    fail_verdict: Any,
    max_tokens: int,
    tier: str,
    *,
    json_mode: bool,
) -> ConsensusResult:
    label = f"aws/{tier}"
    resp, verdict, model_id = _safe_call(
        "aws", tier, system_prompt, user_msg, max_tokens, parse_fn, json_mode=json_mode
    )

    if resp and not verdict:
        logger.warning(
            "Consensus (%s): parse failed (stop_reason=%r text_len=%d) -- retrying",
            label,
            resp.stop_reason,
            len(resp.text or ""),
        )
        retry_msg = (
            user_msg
            + "\n\nSTRICT OUTPUT REMINDER: Return ONLY one valid JSON object. "
            + "No prose, no markdown fences, no explanation."
        )
        resp_retry, retry_verdict, retry_model_id = _safe_call(
            "aws",
            tier,
            system_prompt,
            retry_msg,
            max_tokens,
            parse_fn,
            json_mode=json_mode,
        )
        if retry_verdict:
            resp = resp_retry
            verdict = retry_verdict
            model_id = retry_model_id
            logger.info("Consensus (%s): parse-retry recovered.", label)

    tok = _sum_tokens([resp])
    if not verdict:
        logger.error(
            "Consensus (%s): failed after retry -- returning fail_verdict", label
        )
        return ConsensusResult(
            verdict=fail_verdict,
            reason=f"{label} call/parse failed",
            model_ids=[model_id] if model_id else [],
            **tok,
        )

    logger.info("Consensus (%s): verdict=%s", label, verdict)
    return ConsensusResult(
        verdict=verdict,
        aws_verdict=verdict,
        agreed=True,
        model_ids=[model_id] if model_id else [],
        **tok,
    )


def _dual_model(
    system_prompt: str,
    user_msg: str,
    parse_fn: Callable[[str], Any],
    fail_verdict: Any,
    max_tokens: int,
    arbitrator_tier: str,
    *,
    json_mode: bool,
) -> ConsensusResult:
    """Run AWS small + Azure small in parallel; arbitrate on disagreement."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        aws_future = pool.submit(
            _safe_call,
            "aws",
            "small",
            system_prompt,
            user_msg,
            max_tokens,
            parse_fn,
            json_mode=json_mode,
        )
        az_future = pool.submit(
            _safe_call,
            "azure",
            "small",
            system_prompt,
            user_msg,
            max_tokens,
            parse_fn,
            json_mode=json_mode,
        )
        aws_resp, aws_verdict, aws_model = aws_future.result()
        az_resp, az_verdict, az_model = az_future.result()

    responses: list[LLMResponse | None] = [aws_resp, az_resp]
    model_ids = [m for m in (aws_model, az_model) if m]

    if aws_verdict and az_verdict and aws_verdict == az_verdict:
        tok = _sum_tokens(responses)
        return ConsensusResult(
            verdict=aws_verdict,
            aws_verdict=aws_verdict,
            azure_verdict=az_verdict,
            agreed=True,
            model_ids=model_ids,
            **tok,
        )

    # Disagreement OR at least one provider failed -> arbitrate with big model.
    arb_resp, arb_verdict, arb_model = _safe_call(
        "aws",
        arbitrator_tier,
        system_prompt,
        user_msg,
        max_tokens,
        parse_fn,
        json_mode=json_mode,
    )
    responses.append(arb_resp)
    tok = _sum_tokens(responses)

    if arb_verdict:
        if arb_model:
            model_ids.append(arb_model)
        return ConsensusResult(
            verdict=arb_verdict,
            aws_verdict=aws_verdict or "",
            azure_verdict=az_verdict or "",
            arbitrator_verdict=arb_verdict,
            arbitrator_model_id=arb_model,
            agreed=False,
            single_model_fallback=not (aws_verdict and az_verdict),
            model_ids=model_ids,
            **tok,
        )

    # If arbitrator also failed, surface whichever single-model verdict we do
    # have -- otherwise fall back to fail_verdict.
    fallback_verdict = aws_verdict or az_verdict or fail_verdict
    return ConsensusResult(
        verdict=fallback_verdict,
        aws_verdict=aws_verdict or "",
        azure_verdict=az_verdict or "",
        arbitrator_verdict="",
        reason=(
            "arbitrator failed" if (aws_verdict or az_verdict) else "all models failed"
        ),
        agreed=bool(aws_verdict) and bool(az_verdict) and aws_verdict == az_verdict,
        single_model_fallback=bool(aws_verdict) ^ bool(az_verdict),
        model_ids=model_ids,
        **tok,
    )


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
    """Run the LLM judge in single-model or dual-model mode.

    Dual-model mode is opt-in via ``CONSENSUS_DUAL_MODEL=true`` or
    ``PIPELINE_CONSENSUS_MODE=true``. The arbitrator uses ``CONSENSUS_AWS_TIER``
    (default ``small`` / Haiku, aligned with ``PIPELINE_MODEL_TIER``).

    Args:
        system_prompt: System prompt for the judge.
        user_msg: User message (typically JSON-serialised context).
        parse_fn: Extracts the verdict string from raw LLM output. MUST
            return a falsy value on parse failure.
        fail_verdict: Returned when no provider produces a parseable verdict.
        max_tokens: Max output tokens per call.
        json_mode: Passed through to the provider client.
        tier: Single-model tier override; ignored when dual-model is active.
    """
    if tier is None or tier not in _VALID_CONSENSUS_TIERS:
        tier = _consensus_aws_tier()

    if _dual_model_enabled():
        return _dual_model(
            system_prompt,
            user_msg,
            parse_fn,
            fail_verdict,
            max_tokens,
            arbitrator_tier=_consensus_aws_tier(),
            json_mode=json_mode,
        )

    return _single_model(
        system_prompt,
        user_msg,
        parse_fn,
        fail_verdict,
        max_tokens,
        tier,
        json_mode=json_mode,
    )
