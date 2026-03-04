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
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from libs.llm_client.factory import LLMResponse, create_llm

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    """Outcome of a dual-model consensus check."""

    verdict: str
    confidence: float = 0.0
    reason: str = ""
    aws_verdict: str = ""
    azure_verdict: str = ""
    arbitrator_verdict: str = ""
    arbitrator_model_id: str = ""
    agreed: bool = False
    model_ids: list[str] = field(default_factory=list)


def _call_provider(
    provider: str,
    tier: str,
    system_prompt: str,
    user_msg: str,
    max_tokens: int,
) -> LLMResponse:
    client = create_llm(provider=provider, tier=tier)
    return client.converse(
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.0,
        max_tokens=max_tokens,
    )


def run_consensus(
    *,
    system_prompt: str,
    user_msg: str,
    parse_fn: Callable[[str], str],
    fail_verdict: str,
    max_tokens: int = 150,
) -> ConsensusResult:
    """Run dual-model consensus with Sonnet arbitration on disagreement.

    Args:
        system_prompt: Shared system prompt for all models.
        user_msg: User message (typically JSON-serialised context).
        parse_fn: Extracts the verdict string from raw LLM response text.
                  Must return ``""`` on parse failure.
        fail_verdict: Verdict to return when all LLM calls fail.
        max_tokens: Max output tokens per call.

    Returns:
        ConsensusResult with the agreed or arbitrated verdict.
    """
    aws_verdict = ""
    azure_verdict = ""
    aws_model = ""
    azure_model = ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_aws = pool.submit(
            _call_provider, "aws", "small", system_prompt, user_msg, max_tokens,
        )
        fut_azure = pool.submit(
            _call_provider, "azure", "small", system_prompt, user_msg, max_tokens,
        )

        try:
            aws_resp = fut_aws.result(timeout=60)
            aws_verdict = parse_fn(aws_resp.text)
            aws_model = aws_resp.model_id
        except Exception:
            logger.warning(
                "Consensus AWS small call failed", exc_info=True,
            )

        try:
            azure_resp = fut_azure.result(timeout=60)
            azure_verdict = parse_fn(azure_resp.text)
            azure_model = azure_resp.model_id
        except Exception:
            logger.warning(
                "Consensus Azure small call failed", exc_info=True,
            )

    model_ids = [m for m in (aws_model, azure_model) if m]

    if not aws_verdict and not azure_verdict:
        logger.error("Consensus: both providers failed -- using fail_verdict")
        return ConsensusResult(
            verdict=fail_verdict,
            reason="both providers failed",
            model_ids=model_ids,
        )

    if not aws_verdict:
        return ConsensusResult(
            verdict=azure_verdict,
            azure_verdict=azure_verdict,
            reason="AWS failed; using Azure verdict",
            model_ids=model_ids,
        )
    if not azure_verdict:
        return ConsensusResult(
            verdict=aws_verdict,
            aws_verdict=aws_verdict,
            reason="Azure failed; using AWS verdict",
            model_ids=model_ids,
        )

    if aws_verdict == azure_verdict:
        logger.info(
            "Consensus: both models agree verdict=%s", aws_verdict,
        )
        return ConsensusResult(
            verdict=aws_verdict,
            aws_verdict=aws_verdict,
            azure_verdict=azure_verdict,
            agreed=True,
            model_ids=model_ids,
        )

    # -- Disagreement: Sonnet arbitrates --
    logger.info(
        "Consensus: disagreement aws=%s azure=%s -- escalating to Sonnet",
        aws_verdict,
        azure_verdict,
    )
    try:
        arb_resp = _call_provider(
            "aws", "big", system_prompt, user_msg, max_tokens,
        )
        arb_verdict = parse_fn(arb_resp.text)
        model_ids.append(arb_resp.model_id)
    except Exception:
        logger.error(
            "Consensus: Sonnet arbitration failed -- using fail_verdict",
            exc_info=True,
        )
        return ConsensusResult(
            verdict=fail_verdict,
            aws_verdict=aws_verdict,
            azure_verdict=azure_verdict,
            reason="arbitrator failed after disagreement",
            model_ids=model_ids,
        )

    if not arb_verdict:
        logger.warning("Consensus: arbitrator returned empty verdict")
        return ConsensusResult(
            verdict=fail_verdict,
            aws_verdict=aws_verdict,
            azure_verdict=azure_verdict,
            reason="arbitrator returned unparseable response",
            model_ids=model_ids,
        )

    if arb_verdict not in {aws_verdict, azure_verdict}:
        logger.warning(
            "consensus.arbitrator_third_verdict: arbitrator=%s disagrees with "
            "both aws=%s and azure=%s -- unexpected third verdict; audit required",
            arb_verdict,
            aws_verdict,
            azure_verdict,
        )
    logger.info(
        "Consensus: arbitrator resolved to %s (aws=%s azure=%s)",
        arb_verdict,
        aws_verdict,
        azure_verdict,
    )
    return ConsensusResult(
        verdict=arb_verdict,
        aws_verdict=aws_verdict,
        azure_verdict=azure_verdict,
        arbitrator_verdict=arb_verdict,
        arbitrator_model_id=arb_resp.model_id,
        agreed=False,
        model_ids=model_ids,
    )
