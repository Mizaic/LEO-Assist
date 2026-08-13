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
    One call via ``PIPELINE_MODEL_PROVIDER`` (default Azure / GPT) at the
    configured tier. A second "strict reminder" retry is issued if the first
    call fails to parse. This is the production default because the
    cost/latency of a second panel rarely justifies the marginal accuracy
    gain for these short classification decisions.

Dual-model consensus (opt-in)
    Enable with ``CONSENSUS_DUAL_MODEL=true``. Runs Azure small-tier and Azure
    big-tier judges in parallel. If they agree, the shared verdict wins.
    If they disagree (or one fails), an Azure model at ``CONSENSUS_AWS_TIER``
    (name retained for env compat; defaults to ``PIPELINE_MODEL_TIER``)
    arbitrates.

Tier selection
--------------
``CONSENSUS_AWS_TIER`` -- tier for single-model mode and the dual-model
    arbitrator (default ``small``). When unset, falls back to
    ``PIPELINE_MODEL_TIER`` (also ``small`` in container defaults).
``CONSENSUS_VERIFIER_TIER`` -- tier used when the caller passes the verifier
    override (``tier=_consensus_verifier_tier()``). Falls back to
    ``CONSENSUS_AWS_TIER`` if unset.
``PIPELINE_CONSENSUS_MODE`` -- when ``true``, enables dual-model mode (same as
    ``CONSENSUS_DUAL_MODEL=true``). Defaults to ``false``.

``ConsensusResult`` fields are kept for API compatibility -- ``aws_verdict``
holds the primary panel (single-model, or Azure small in dual mode) and
``azure_verdict`` holds the secondary panel (Azure big in dual mode).
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from libs.llm_client.factory import LLMResponse, create_llm, default_llm_provider

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
    """Dual-model (Azure small + Azure big, arbitrator on disagree) is opt-in."""
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


@dataclass(frozen=True)
class ConsensusOptions:
    """Provider-neutral controls for a consensus request."""

    max_tokens: int = 150
    json_mode: bool = False
    tier: str | None = None
    structured_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class _ConsensusRequest:
    system_prompt: str
    user_msg: str
    parse_fn: Callable[[str], Any]
    fail_verdict: Any
    options: ConsensusOptions


def _call_provider(
    provider: str,
    tier: str,
    request: _ConsensusRequest,
) -> LLMResponse:
    client = create_llm(provider=provider, tier=tier)
    return client.converse(
        system=request.system_prompt,
        messages=[{"role": "user", "content": request.user_msg}],
        temperature=0.0,
        max_tokens=request.options.max_tokens,
        json_mode=request.options.json_mode,
        structured_schema=request.options.structured_schema,
        verbosity="low",
        agent_task="consensus",
        patient_id="",
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
    request: _ConsensusRequest,
) -> tuple[LLMResponse | None, Any, str]:
    """Call a single provider and return ``(response, verdict, model_id)``.

    Any provider error becomes ``(None, None, "")`` -- callers decide how to
    degrade.
    """
    try:
        resp = _call_provider(provider, tier, request)
    except Exception:
        logger.warning("Consensus (%s/%s): call failed", provider, tier, exc_info=True)
        return None, None, ""
    verdict = request.parse_fn(resp.text) if resp else None
    return resp, verdict, (resp.model_id if resp else "")


def _single_model(request: _ConsensusRequest, tier: str) -> ConsensusResult:
    provider = default_llm_provider()
    label = f"{provider}/{tier}"
    resp, verdict, model_id = _safe_call(provider, tier, request)

    if resp and not verdict:
        logger.warning(
            "Consensus (%s): parse failed (stop_reason=%r text_len=%d) -- retrying",
            label,
            resp.stop_reason,
            len(resp.text or ""),
        )
        retry_msg = (
            request.user_msg
            + "\n\nSTRICT OUTPUT REMINDER: Return ONLY one valid JSON object. "
            + "No prose, no markdown fences, no explanation."
        )
        retry_request = _ConsensusRequest(
            system_prompt=request.system_prompt,
            user_msg=retry_msg,
            parse_fn=request.parse_fn,
            fail_verdict=request.fail_verdict,
            options=request.options,
        )
        resp_retry, retry_verdict, retry_model_id = _safe_call(
            provider, tier, retry_request
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
            verdict=request.fail_verdict,
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


def _dual_model(request: _ConsensusRequest, arbitrator_tier: str) -> ConsensusResult:
    """Run Azure small + Azure big in parallel; arbitrate on disagreement."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        primary_future = pool.submit(
            _safe_call,
            "azure",
            "small",
            request,
        )
        secondary_future = pool.submit(
            _safe_call,
            "azure",
            "big",
            request,
        )
        primary_resp, primary_verdict, primary_model = primary_future.result()
        secondary_resp, secondary_verdict, secondary_model = secondary_future.result()

    responses: list[LLMResponse | None] = [primary_resp, secondary_resp]
    model_ids = [m for m in (primary_model, secondary_model) if m]

    if primary_verdict and secondary_verdict and primary_verdict == secondary_verdict:
        tok = _sum_tokens(responses)
        return ConsensusResult(
            verdict=primary_verdict,
            aws_verdict=primary_verdict,
            azure_verdict=secondary_verdict,
            agreed=True,
            model_ids=model_ids,
            **tok,
        )

    # Disagreement OR at least one panel failed -> arbitrate.
    arb_resp, arb_verdict, arb_model = _safe_call("azure", arbitrator_tier, request)
    responses.append(arb_resp)
    tok = _sum_tokens(responses)

    if arb_verdict:
        if arb_model:
            model_ids.append(arb_model)
        return ConsensusResult(
            verdict=arb_verdict,
            aws_verdict=primary_verdict or "",
            azure_verdict=secondary_verdict or "",
            arbitrator_verdict=arb_verdict,
            arbitrator_model_id=arb_model,
            agreed=False,
            single_model_fallback=not (primary_verdict and secondary_verdict),
            model_ids=model_ids,
            **tok,
        )

    fallback_verdict = primary_verdict or secondary_verdict or request.fail_verdict
    return ConsensusResult(
        verdict=fallback_verdict,
        aws_verdict=primary_verdict or "",
        azure_verdict=secondary_verdict or "",
        arbitrator_verdict="",
        reason=(
            "arbitrator failed"
            if (primary_verdict or secondary_verdict)
            else "all models failed"
        ),
        agreed=(
            bool(primary_verdict)
            and bool(secondary_verdict)
            and primary_verdict == secondary_verdict
        ),
        single_model_fallback=bool(primary_verdict) ^ bool(secondary_verdict),
        model_ids=model_ids,
        **tok,
    )


def run_consensus(
    *,
    system_prompt: str,
    user_msg: str,
    parse_fn: Callable[[str], Any],
    fail_verdict: Any,
    options: ConsensusOptions | None = None,
) -> ConsensusResult:
    """Run the LLM judge in single-model or dual-model mode.

    Dual-model mode is opt-in via ``CONSENSUS_DUAL_MODEL=true`` or
    ``PIPELINE_CONSENSUS_MODE=true``. The arbitrator uses ``CONSENSUS_AWS_TIER``
    (default ``small``, aligned with ``PIPELINE_MODEL_TIER``) on Azure.

    Args:
        system_prompt: System prompt for the judge.
        user_msg: User message (typically JSON-serialised context).
        parse_fn: Extracts the verdict string from raw LLM output. MUST
            return a falsy value on parse failure.
        fail_verdict: Returned when no provider produces a parseable verdict.
        options: Output, tier and strict-schema controls.
    """
    config = options or ConsensusOptions()
    tier = config.tier
    if tier is None or tier not in _VALID_CONSENSUS_TIERS:
        tier = _consensus_aws_tier()
    request = _ConsensusRequest(
        system_prompt=system_prompt,
        user_msg=user_msg,
        parse_fn=parse_fn,
        fail_verdict=fail_verdict,
        options=config,
    )

    if _dual_model_enabled():
        return _dual_model(
            request,
            arbitrator_tier=_consensus_aws_tier(),
        )

    return _single_model(request, tier)
