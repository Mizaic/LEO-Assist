"""Token-budget aware shrinker for the SBAR Background prompt.

Today libs/sbar/prompt_calls.py applies only a per-source 4000-char
cap. A patient with many long encounters or chunked discharge
summaries can easily produce a prompt that exceeds the Bedrock
Claude input window, at which point the LLM call returns a
ValidationException ("Input is too long for requested model") and
the run silently degrades to a partial SBAR.

This module is a pure function over the resolved Background sources
that:

  1. Estimates the prompt's token count using a conservative
     char/token heuristic (default 3.6 chars per token).
  2. Computes a budget = SBAR_BACKGROUND_MAX_INPUT_TOKENS minus a
     fixed margin for the system prompt and model overhead.
  3. Progressively reduces the per-source cap from 4000 through
     2000, 1000, 500 and 250 until the estimated tokens fit.
  4. If still over budget, drops sources from the end of the list
     until the prompt fits or only one source remains.
  5. Returns a plain-English notice (reading age 9-11) when any
     trimming happened.

See DI-LEO-AI-513 / DO-LEO-AI-515.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource

logger = logging.getLogger(__name__)


# Conservative -- 3.6 chars per token under-counts for non-English /
# code, so the resulting estimate is a slight over-estimate of the
# real token count, which is what we want for a budget gate.
_CHARS_PER_TOKEN = 3.6


# Progressive caps. The first cap matches the legacy 4000-char cap so
# under-budget runs are a no-op.
_PROGRESSIVE_CAPS: tuple[int, ...] = (4000, 2000, 1000, 500, 250)


# Reserved budget for the system prompt + model overhead (header,
# JSON wrapper, codes block etc.). Picked to be safely large for the
# v2 Background system prompt; if we ever change that prompt
# substantially we should re-tune this.
_SYSTEM_PROMPT_RESERVE_TOKENS = 4000


_ENV_FLOOR_TOKENS = 1000


def _max_input_tokens() -> int:
    """Read SBAR_BACKGROUND_MAX_INPUT_TOKENS from the environment.

    Default 60_000 is well below Claude 3.5 Sonnet's 200K input
    window so we leave headroom for the response. Tune via env when
    pointing at a smaller / cheaper model. A floor of
    ``_ENV_FLOOR_TOKENS`` prevents an empty / nonsense env var from
    collapsing the budget; explicit ``max_input_tokens`` arguments
    are respected as-is so tests can exercise extreme paths.
    """
    raw = os.getenv("SBAR_BACKGROUND_MAX_INPUT_TOKENS", "60000")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "SBAR_BACKGROUND_MAX_INPUT_TOKENS=%r is not an int; using 60000",
            raw,
        )
        return 60000
    return max(_ENV_FLOOR_TOKENS, value)


def _estimate_tokens(text: str) -> int:
    """Cheap char-based token estimate. Over-estimates slightly."""
    if not text:
        return 0
    return int(len(text) / _CHARS_PER_TOKEN) + 1


@dataclass
class ShrinkReport:
    """Audit record of what the shrinker did to the Background prompt."""

    original_source_count: int
    kept_source_count: int
    dropped_source_ids: list[str] = field(default_factory=list)
    per_source_char_cap: int = _PROGRESSIVE_CAPS[0]
    estimated_input_tokens: int = 0
    notice: str | None = None

    def trimmed(self) -> bool:
        return self.notice is not None


def _serialise(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None,
    cap: int,
) -> str:
    """Same shape as libs/sbar/prompt_calls._serialise_background_context."""
    body: dict[str, Any] = {
        "referring_specialty": referring_specialty,
        "codes": [
            {
                "concept_id": c.concept_id,
                "term": c.term,
                "semantic_tag": c.semantic_tag,
                "assertion": c.assertion,
                "evidence": sanitise_for_prompt(c.evidence or ""),
                "source": {"type": c.source_label, "id": c.source_id},
                "confidence": c.confidence,
            }
            for c in codes
        ],
        "sources": [
            {
                "type": s.source_label,
                "id": s.source_id,
                "text": sanitise_for_prompt(s.text or "")[:cap],
                "metadata": s.metadata,
                "has_codes": s.has_codes(),
            }
            for s in sources
        ],
    }
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _build_notice(
    *,
    cap: int,
    dropped_ids: list[str],
    original_count: int,
) -> str | None:
    """Plain-English notice. Reading age 9-11. Active voice."""
    if cap == _PROGRESSIVE_CAPS[0] and not dropped_ids:
        return None
    parts: list[str] = []
    if cap < _PROGRESSIVE_CAPS[0]:
        parts.append(
            f"Some records were too long, so we shortened each one to "
            f"{cap} characters before asking the AI to write Background."
        )
    if dropped_ids:
        kept = original_count - len(dropped_ids)
        parts.append(
            f"There was still too much to fit, so we dropped "
            f"{len(dropped_ids)} of {original_count} records and kept the "
            f"first {kept}. Pick fewer records if you want all of them used."
        )
    return " ".join(parts) if parts else None


def shrink_background_context(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None = None,
    max_input_tokens: int | None = None,
    system_prompt_reserve_tokens: int = _SYSTEM_PROMPT_RESERVE_TOKENS,
) -> tuple[str, ShrinkReport]:
    """Build the Background user message, shrinking until it fits.

    Pure function -- no LLM calls, no Neo4j queries. Safe to call
    from tests and from the prompt-call layer.

    Returns:
        (serialised_user_message, ShrinkReport)
    """
    budget = max_input_tokens if max_input_tokens is not None else _max_input_tokens()
    budget = max(1, budget - system_prompt_reserve_tokens)

    original_count = len(sources)
    kept = list(sources)
    dropped_ids: list[str] = []

    chosen_cap = _PROGRESSIVE_CAPS[0]
    serialised = ""
    estimated = 0

    for cap in _PROGRESSIVE_CAPS:
        chosen_cap = cap
        serialised = _serialise(
            kept, codes, referring_specialty=referring_specialty, cap=cap
        )
        estimated = _estimate_tokens(serialised)
        if estimated <= budget:
            break

    while estimated > budget and len(kept) > 1:
        dropped = kept.pop()
        dropped_ids.append(dropped.source_id)
        serialised = _serialise(
            kept,
            codes,
            referring_specialty=referring_specialty,
            cap=chosen_cap,
        )
        estimated = _estimate_tokens(serialised)

    notice = _build_notice(
        cap=chosen_cap,
        dropped_ids=dropped_ids,
        original_count=original_count,
    )

    report = ShrinkReport(
        original_source_count=original_count,
        kept_source_count=len(kept),
        dropped_source_ids=dropped_ids,
        per_source_char_cap=chosen_cap,
        estimated_input_tokens=estimated,
        notice=notice,
    )
    if notice:
        logger.info(
            "SBAR background shrinker: trimmed cap=%d kept=%d "
            "dropped=%d est_tokens=%d budget=%d",
            chosen_cap,
            len(kept),
            len(dropped_ids),
            estimated,
            budget,
        )
    return serialised, report
