"""Verdict ladder for the AI first-pass.

Atlas trace:
  DO: DO-D7005C41
  DI: DI-0FFA05BB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D7005C41")

DI-LEO-AI-208 / DO-LEO-AI-205.

Reuses the safety rails defined in services.api.app.services.candidate_prune
(keeps the rail vocabulary aligned across both workflows).
"""

from __future__ import annotations

from typing import Any

from services.api.app.services.candidate_prune import (
    SAFETY_RAIL_BLOCKED_ASSERTION,
    SAFETY_RAIL_MANUAL_SEED,
    SAFETY_RAIL_ZERO_ENTITIES,
    _AUTO_CODE_BLOCKED,
    _MANUAL_SEED_PREFIX,
)

from ._types import (
    AIFirstPassVerdict,
    CandidateOutcome,
    CodingOutcome,
    ExtractionResult,
)

# Additional rail: the candidate's live status came back as 'completed'
# at any point. This MUST short-circuit to verdict='review' even though
# the writeback layer also re-checks (defence in depth).
SAFETY_RAIL_LIVE_COMPLETED = "live_completed_safety_rail"


def _count_blocked_assertions(extraction: ExtractionResult) -> int:
    n = 0
    for ent in extraction.entities:
        if (ent.assertion or "").strip().lower() in _AUTO_CODE_BLOCKED:
            n += 1
    return n


def classify_candidate(
    candidate: dict[str, Any],
    extraction: ExtractionResult,
    codings: list[CodingOutcome],
) -> CandidateOutcome:
    """Decide the AI-first-pass verdict for one candidate.

    Verdict ladder:
      1. Safety rail: status is currently 'completed' -> review.
      2. Safety rail: zero entities after the AI pass -> review.
      3. Safety rail: any blocked assertion -> review.
      4. Safety rail: source is a manual gold seed -> review.
      5. accepted_count > 0 AND rejected_count == 0 -> pre_done.
      6. accepted_count > 0 AND rejected_count > 0 -> pre_done
         (the user wants any successfully-coded entity to keep the
         candidate; rejections are visible in the dialog so the
         reviewer can confirm or revert).
      7. accepted_count == 0 AND rejected_count > 0 -> delete.
      8. accepted_count == 0 AND rejected_count == 0 -> review
         (defensive; should already have been caught by rail 2).
    """
    candidate_id = str(candidate.get("candidate_id") or "")
    status = str(candidate.get("status") or "")
    source = str(candidate.get("source") or "")
    text = str(candidate.get("text") or "")

    rejection_reasons: list[str] = []

    def _outcome(verdict: AIFirstPassVerdict, *reasons: str) -> CandidateOutcome:
        return CandidateOutcome(
            candidate_id=candidate_id,
            status=status,
            source=source,
            text=text,
            verdict=verdict,
            action="skipped_review",  # action filled by the writeback caller
            extraction=extraction,
            codings=list(codings),
            rejection_reasons=[*rejection_reasons, *reasons],
        )

    if status == "completed":
        return _outcome("review", SAFETY_RAIL_LIVE_COMPLETED)

    if extraction.entity_count == 0:
        return _outcome("review", SAFETY_RAIL_ZERO_ENTITIES)

    if _count_blocked_assertions(extraction) > 0:
        return _outcome("review", SAFETY_RAIL_BLOCKED_ASSERTION)

    if source.startswith(_MANUAL_SEED_PREFIX):
        return _outcome("review", SAFETY_RAIL_MANUAL_SEED)

    accepted = sum(1 for c in codings if c.accepted)
    rejected = sum(1 for c in codings if not c.accepted)

    rejection_reasons.extend(
        sorted({c.rejection_reason for c in codings if not c.accepted and c.rejection_reason})
    )

    if accepted > 0:
        return _outcome("pre_done")
    if rejected > 0:
        return _outcome("delete")
    return _outcome("review", "no_codings_produced")
