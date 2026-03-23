"""Dual-model consensus runner with arbitration.

Standard verification pattern:
  1. Run Haiku (AWS small) and GPT-5 mini (Azure small) in parallel.
  2. If both agree, use that verdict.
  3. If they disagree, Sonnet (AWS big) arbitrates.

The caller provides a ``parse_fn`` that extracts the verdict string from the
raw LLM response text, and a ``fail_verdict`` that is returned when all
calls fail.  This keeps the module generic -- the same runner works for
disorder verification, coding confidence checks, and any future gate.
"""

from __future__ import annotations

import concurrent.futures
import json as _json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from libs.llm_client.factory import LLMResponse, create_llm

logger = logging.getLogger(__name__)


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


def _normalise_verdict(verdict: Any) -> str:
    """Normalise a verdict to a canonical string for equality comparison.

    Converts the verdict to JSON with keys and any string-only lists sorted so
    that ordering differences between models (e.g. same SNOMED terms returned
    in a different order, or dict keys in a different order) do not trigger
    unnecessary Sonnet arbitration.

    Works correctly for:
    - Simple string verdicts
    - Flat dicts with string/int values
    - Nested structures such as ``criteria_groups`` (list of dicts) — these are
      serialised to JSON and the whole blob is sorted, avoiding the ``TypeError:
      '<' not supported between instances of 'dict' and 'dict'`` that ``sorted()``
      raises when list elements are dicts.
    """
    def _sort_obj(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _sort_obj(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            items = [_sort_obj(i) for i in obj]
            try:
                # Try sorting directly (works for lists of scalars).
                return sorted(items)  # type: ignore[type-var]
            except TypeError:
                # Elements are dicts or other non-comparable types — sort by their
                # JSON representation so the comparison is stable and deterministic.
                return sorted(items, key=lambda x: _json.dumps(x, sort_keys=True, ensure_ascii=False))
        return obj

    return _json.dumps(_sort_obj(verdict), sort_keys=True, ensure_ascii=False)


def _fmt_verdict(v: Any) -> str:
    """Serialise a verdict to a compact string for embedding in a prompt."""
    if isinstance(v, dict):
        return _json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return str(v) if v is not None else "null"


def _call_arbitrator(
    system_prompt: str,
    user_msg: str,
    aws_verdict: Any,
    azure_verdict: Any,
    max_tokens: int,
) -> tuple[LLMResponse, str]:
    """Call the big-model arbitrator with a guided prompt.

    The arbitration message shows both small-model verdicts explicitly and
    instructs the model to choose one and return ONLY JSON.  The instruction
    to begin the response with ``{`` is embedded in the user message because
    Claude Sonnet on Bedrock does not support assistant message prefill
    (the Converse API requires the conversation to end with a user turn).

    Returns:
        ``(response, full_text)`` where ``full_text`` is the raw response text.
    """
    arb_msg = (
        f"{user_msg}\n\n"
        "---\n"
        "Two models returned slightly different answers for the task above. "
        "Review both and return the single most clinically accurate result. "
        "Your response must be ONLY a valid JSON object — start your reply with "
        "'{' and include no explanation, markdown, or preamble whatsoever:\n\n"
        f"Model A: {_fmt_verdict(aws_verdict)}\n"
        f"Model B: {_fmt_verdict(azure_verdict)}"
    )
    resp = _call_provider(
        "aws",
        "big",
        system_prompt,
        arb_msg,
        max_tokens,
        json_mode=False,
    )
    return resp, resp.text or ""


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
) -> ConsensusResult:
    """Run dual-model consensus with Sonnet arbitration on disagreement.

    Agreement check
    ---------------
    List-valued fields inside dict verdicts are sorted before comparison so
    that ordering differences (e.g. models returning the same SNOMED terms in
    different order) do not trigger unnecessary Sonnet arbitration.

    Arbitration resilience
    ----------------------
    When the arbitrator returns an empty / unparseable response (a transient
    Bedrock issue observed with ``claude-sonnet-4-6``), the call is retried
    once.  If both attempts fail the runner falls back to ``aws_verdict``
    (when available) rather than ``fail_verdict`` — this preserves valid data
    from the small models instead of silently discarding it.

    Token tracking
    --------------
    Every ``LLMResponse`` returned by each provider call is accumulated into
    the ``ConsensusResult`` token fields so callers can write ``AuditEvent``
    nodes without re-instrumenting the provider layer.

    Args:
        system_prompt: Shared system prompt for all models.
        user_msg: User message (typically JSON-serialised context).
        parse_fn: Extracts the verdict from raw LLM response text.
                  Must return a falsy value (``""`` or ``None``) on parse
                  failure.  The verdict may be any type (str, dict, etc.);
                  consensus uses ``==`` comparison after list-normalisation,
                  not hashing.
        fail_verdict: Verdict to return when ALL calls fail (including both
                      small models AND both arbitrator attempts).
        max_tokens: Max output tokens per call.

    Returns:
        ConsensusResult with the agreed or arbitrated verdict and token totals.
    """
    aws_verdict: Any = ""
    azure_verdict: Any = ""
    aws_model = ""
    azure_model = ""
    aws_resp: LLMResponse | None = None
    azure_resp: LLMResponse | None = None
    aws_call_failed = False
    azure_call_failed = False
    aws_parse_failed = False
    azure_parse_failed = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_aws = pool.submit(
            _call_provider, "aws", "small", system_prompt, user_msg, max_tokens, json_mode=json_mode,
        )
        fut_azure = pool.submit(
            _call_provider, "azure", "small", system_prompt, user_msg, max_tokens, json_mode=json_mode,
        )

        try:
            aws_resp = fut_aws.result(timeout=60)
            aws_verdict = parse_fn(aws_resp.text)
            aws_model = aws_resp.model_id
            aws_parse_failed = not bool(aws_verdict)
            if aws_parse_failed:
                logger.warning(
                    "Consensus AWS small call parse-failed (model=%s stop_reason=%r text_len=%d)",
                    aws_resp.model_id,
                    aws_resp.stop_reason,
                    len(aws_resp.text or ""),
                )
        except Exception:
            aws_call_failed = True
            logger.warning("Consensus AWS small call failed", exc_info=True)

        try:
            azure_resp = fut_azure.result(timeout=60)
            azure_verdict = parse_fn(azure_resp.text)
            azure_model = azure_resp.model_id
            azure_parse_failed = not bool(azure_verdict)
            if azure_parse_failed:
                logger.warning(
                    "Consensus Azure small call parse-failed (model=%s stop_reason=%r text_len=%d)",
                    azure_resp.model_id,
                    azure_resp.stop_reason,
                    len(azure_resp.text or ""),
                )
        except Exception:
            azure_call_failed = True
            logger.warning("Consensus Azure small call failed", exc_info=True)

    # One targeted parse-retry for JSON-mode prompts (most extraction/verifier calls).
    # This addresses empty/non-parseable provider output without conflating it with
    # transport/provider failures.
    if json_mode and aws_parse_failed and not aws_call_failed:
        try:
            retry_msg = (
                user_msg
                + "\n\nSTRICT OUTPUT REMINDER: Return ONLY one valid JSON object. "
                + "No prose, no markdown fences, no explanation."
            )
            aws_resp_retry = _call_provider(
                "aws",
                "small",
                system_prompt,
                retry_msg,
                max_tokens,
                json_mode=True,
            )
            aws_verdict = parse_fn(aws_resp_retry.text)
            if aws_verdict:
                aws_resp = aws_resp_retry
                aws_parse_failed = False
                aws_model = aws_resp_retry.model_id
                logger.info("Consensus AWS small parse-retry recovered.")
        except Exception:
            logger.warning("Consensus AWS small parse-retry failed", exc_info=True)

    if json_mode and azure_parse_failed and not azure_call_failed:
        try:
            retry_msg = (
                user_msg
                + "\n\nSTRICT OUTPUT REMINDER: Return ONLY one valid JSON object. "
                + "No prose, no markdown fences, no explanation."
            )
            azure_resp_retry = _call_provider(
                "azure",
                "small",
                system_prompt,
                retry_msg,
                max_tokens + 400,
                json_mode=True,
            )
            azure_verdict = parse_fn(azure_resp_retry.text)
            if azure_verdict:
                azure_resp = azure_resp_retry
                azure_parse_failed = False
                azure_model = azure_resp_retry.model_id
                logger.info("Consensus Azure small parse-retry recovered.")
        except Exception:
            logger.warning("Consensus Azure small parse-retry failed", exc_info=True)

    model_ids = [m for m in (aws_model, azure_model) if m]
    provider_resps: list[LLMResponse | None] = [aws_resp, azure_resp]

    def _make_result(**kwargs) -> ConsensusResult:
        """Build a ConsensusResult with aggregated token totals from all calls."""
        all_resps = provider_resps + kwargs.pop("_extra_resps", [])
        tok = _sum_tokens(all_resps)
        return ConsensusResult(
            input_tokens=tok["input_tokens"],
            output_tokens=tok["output_tokens"],
            cached_input_tokens=tok["cached_input_tokens"],
            llm_calls=tok["llm_calls"],
            **kwargs,
        )

    if not aws_verdict and not azure_verdict:
        logger.error("Consensus: both providers failed -- using fail_verdict")
        return _make_result(
            verdict=fail_verdict,
            reason="both providers failed",
            model_ids=model_ids,
        )

    if not aws_verdict:
        logger.warning(
            "Consensus: AWS provider %s — using Azure verdict only. "
            "Output is UNVALIDATED (single-model). Rule will be flagged for mandatory human review.",
            "CALL_FAILED" if aws_call_failed else "PARSE_FAILED",
        )
        return _make_result(
            verdict=azure_verdict,
            azure_verdict=azure_verdict,
            reason="AWS failed; using Azure verdict (unvalidated single-model output)",
            single_model_fallback=True,
            model_ids=model_ids,
        )
    if not azure_verdict:
        logger.warning(
            "Consensus: Azure provider %s — using AWS verdict only. "
            "Output is UNVALIDATED (single-model). Rule will be flagged for mandatory human review.",
            "CALL_FAILED" if azure_call_failed else "PARSE_FAILED",
        )
        return _make_result(
            verdict=aws_verdict,
            aws_verdict=aws_verdict,
            reason="Azure failed; using AWS verdict (unvalidated single-model output)",
            single_model_fallback=True,
            model_ids=model_ids,
        )

    # Agreement check — normalise list ordering before comparing so that
    # models returning the same terms in different order are not escalated.
    if _normalise_verdict(aws_verdict) == _normalise_verdict(azure_verdict):
        logger.info("Consensus: both models agree verdict=%s", aws_verdict)
        return _make_result(
            verdict=aws_verdict,
            aws_verdict=aws_verdict,
            azure_verdict=azure_verdict,
            agreed=True,
            model_ids=model_ids,
        )

    # -- Disagreement: Sonnet arbitrates (up to 2 attempts) --
    logger.info(
        "Consensus: disagreement aws=%s azure=%s -- escalating to Sonnet",
        aws_verdict,
        azure_verdict,
    )

    arb_verdict: Any = None
    arb_model_id = ""
    arb_stop_reason = ""
    arb_resps: list[LLMResponse | None] = []

    for attempt in range(1, 3):  # attempts 1 and 2
        try:
            arb_resp, arb_text = _call_arbitrator(
                system_prompt, user_msg, aws_verdict, azure_verdict, max_tokens,
            )
            arb_resps.append(arb_resp)
            arb_model_id = arb_resp.model_id
            arb_stop_reason = arb_resp.stop_reason
            if arb_model_id not in model_ids:
                model_ids.append(arb_model_id)
            arb_verdict = parse_fn(arb_text)
        except Exception:
            logger.error(
                "Consensus: Sonnet arbitration attempt %d raised exception",
                attempt, exc_info=True,
            )
            arb_verdict = None
            arb_text = ""
            arb_stop_reason = "exception"

        if arb_verdict:
            break

        logger.warning(
            "Consensus: arbitrator attempt %d returned empty verdict "
            "(stop_reason=%r, text_len=%d)%s",
            attempt,
            arb_stop_reason,
            len(arb_text or ""),
            " -- retrying" if attempt == 1 else "",
        )

    if not arb_verdict:
        # Both arbitration attempts failed.  The two small models DISAGREED and
        # arbitration could not resolve it.  We must NOT fall back to a single
        # model's unvalidated output — the whole point of consensus is that neither
        # model's answer has been confirmed.  Return fail_verdict so the caller
        # can treat this as a hard failure and NOT write the rule to Neo4j.
        logger.error(
            "Consensus: arbitrator FAILED after 2 attempts — returning fail_verdict. "
            "The two models DISAGREED (aws=%s, azure=%s) and arbitration could not resolve it. "
            "Rule will NOT be written to Neo4j. Investigate Sonnet availability.",
            aws_verdict, azure_verdict,
        )
        return _make_result(
            verdict=fail_verdict,
            aws_verdict=aws_verdict,
            azure_verdict=azure_verdict,
            reason=(
                "arbitrator failed after 2 attempts on a disagreement; "
                "unparseable/empty arbitrator output; returning fail_verdict"
            ),
            model_ids=model_ids,
            _extra_resps=arb_resps,
        )

    if arb_verdict not in (aws_verdict, azure_verdict):
        logger.error(
            "consensus.arbitrator_third_verdict: arbitrator=%s disagrees with BOTH "
            "aws=%s AND azure=%s — novel third verdict produced. "
            "AUDIT REQUIRED: this extraction must be manually reviewed.",
            arb_verdict, aws_verdict, azure_verdict,
        )
    logger.info(
        "Consensus: arbitrator resolved to %s (aws=%s azure=%s)",
        arb_verdict,
        aws_verdict,
        azure_verdict,
    )
    return _make_result(
        verdict=arb_verdict,
        aws_verdict=aws_verdict,
        azure_verdict=azure_verdict,
        arbitrator_verdict=arb_verdict,
        arbitrator_model_id=arb_model_id,
        agreed=False,
        model_ids=model_ids,
        _extra_resps=arb_resps,
    )
