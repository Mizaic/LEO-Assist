"""AI first-pass over the TrainingCandidate backlog (UN-LEO-AI-085).

Public API:
  AIFirstPassParams   -- caller-supplied tunables.
  CandidateOutcome    -- per-candidate result (verdict + action + codings).
  ai_extract_entities -- Haiku + few-shot extractor.
  ai_code_entity      -- per-entity validator + Haiku alt-query loop.
  classify_candidate  -- verdict ladder.
  writeback_pre_done  -- persist pre_done overrides (+ audit copy).
  execute_delete      -- TOCTOU-defended delete.
  process_one         -- orchestrate extract -> code -> classify -> apply.
  fetch_candidates    -- paginate non-completed candidates.

The job runner is exported separately (``_job_runner``) so callers
that just want the per-candidate engine don't pay the threading cost.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from libs.terminology.client import TerminologyClient

from ._coder import ai_code_entity
from ._extractor import ai_extract_entities
from ._gold_pool import (
    cache_size,
    get_few_shot_selector,
    invalidate_cache,
    load_gold_pool_rows,
)
from ._types import (
    AIFirstPassParams,
    AIFirstPassVerdict,
    AIFirstPassAction,
    CandidateOutcome,
    CodingOutcome,
    ExtractedEntity,
    ExtractionResult,
)
from ._verdict import classify_candidate
from ._writeback import (
    build_pre_done_entities_payload,
    execute_delete,
    writeback_pre_done,
)

logger = logging.getLogger(__name__)


def fetch_candidates(
    client: Any,
    params: AIFirstPassParams,
) -> list[dict[str, Any]]:
    """Reuse the existing prune-service fetcher (status='completed' excluded)."""
    from services.api.app.services.candidate_prune import (
        fetch_non_completed_candidates,
    )

    return fetch_non_completed_candidates(
        client, statuses=params.statuses, limit=params.limit
    )


def process_one(
    candidate: dict[str, Any],
    *,
    client: Any,
    terminology: TerminologyClient,
    selector: Any,
    params: AIFirstPassParams,
    run_id: str,
) -> CandidateOutcome:
    """End-to-end pass for a single candidate.

    Order:
      1. ai_extract_entities (Haiku + few-shot; fallback on failure)
      2. ai_code_entity per extracted entity
      3. classify_candidate (verdict)
      4. apply: writeback_pre_done | execute_delete | no-op
    """
    extraction = ai_extract_entities(
        candidate=candidate,
        selector=selector,
        k=params.few_shot_k,
        tier=params.haiku_tier,
    )

    encounter_text = str(candidate.get("text") or "")
    codings: list[CodingOutcome] = []
    for ent in extraction.entities:
        codings.append(
            ai_code_entity(
                ent,
                terminology,
                encounter_text=encounter_text,
                validator_kwargs=params.validator_kwargs(),
                max_retries=params.coder_max_retries,
                haiku_tier=params.haiku_tier,
            )
        )

    outcome = classify_candidate(candidate, extraction, codings)

    if params.dry_run:
        outcome.action = "skipped_review"
        return outcome

    try:
        if outcome.verdict == "pre_done":
            payload = build_pre_done_entities_payload(
                extraction.entities, codings, run_id=run_id
            )
            res = writeback_pre_done(
                client,
                candidate_id=outcome.candidate_id,
                entities_payload=payload,
                run_id=run_id,
            )
            outcome.action = res.get("action", "error")
        elif outcome.verdict == "delete":
            res = execute_delete(client, outcome.candidate_id)
            outcome.action = res.get("action", "error")
        else:
            outcome.action = "skipped_review"
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "AI first-pass apply failed for candidate=%s", outcome.candidate_id
        )
        outcome.action = "error"
        outcome.error = f"{type(exc).__name__}: {exc}"

    return outcome


def summarise(outcomes: Iterable[CandidateOutcome]) -> dict[str, Any]:
    by_verdict: dict[str, int] = {"pre_done": 0, "delete": 0, "review": 0}
    by_action: dict[str, int] = {}
    errors = 0
    n = 0
    for o in outcomes:
        n += 1
        by_verdict[o.verdict] = by_verdict.get(o.verdict, 0) + 1
        by_action[o.action] = by_action.get(o.action, 0) + 1
        if o.error:
            errors += 1
    return {
        "candidate_count": n,
        "by_verdict": by_verdict,
        "by_action": by_action,
        "errors": errors,
    }


__all__ = [
    "AIFirstPassParams",
    "AIFirstPassVerdict",
    "AIFirstPassAction",
    "CandidateOutcome",
    "CodingOutcome",
    "ExtractedEntity",
    "ExtractionResult",
    "ai_code_entity",
    "ai_extract_entities",
    "build_pre_done_entities_payload",
    "cache_size",
    "classify_candidate",
    "execute_delete",
    "fetch_candidates",
    "get_few_shot_selector",
    "invalidate_cache",
    "load_gold_pool_rows",
    "process_one",
    "summarise",
    "writeback_pre_done",
]
