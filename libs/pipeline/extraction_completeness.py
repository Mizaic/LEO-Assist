"""Say so when extraction read less than the whole letter.

A run can read part of a referral and still hand back something shaped
exactly like a complete extraction. Findings in the unread part come
back absent, and absent reads as "not present" to whoever picks the
referral up. Failing to look and finding nothing must not produce the
same output.

Two paths can read short, and both use the words here so a reviewer
sees one message:

- the windowed path, when a window fails or will not fit its budget
  (``libs.pipeline.windowed_llm_extraction``)
- the full-document path, when the letter is longer than the
  character budget for a single prompt
  (``libs.pipeline_graph.subgraphs.extraction``)

Rule: .cursor/rules/fail-closed-boundary.mdc rule 3 -- partial results
are typed as partial.

Atlas trace:
  DI: DI-B7A69F26
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B7A69F26")
"""

from __future__ import annotations

from typing import Any

INCOMPLETE_EXTRACTION_WARNING = "extraction_incomplete"


def short_read_fields(reasons: list[str]) -> dict[str, Any]:
    """Return the state fields that type a run as a short read.

    Returns an empty dict when there is nothing to report, so callers
    can splat it into a result without a branch.
    """
    kept = [str(reason).strip() for reason in reasons if str(reason).strip()]
    if not kept:
        return {}
    return {
        "extraction_partial": True,
        "warnings": [
            f"{INCOMPLETE_EXTRACTION_WARNING}: a person needs to check this "
            f"referral against the letter. We did not read all of it: "
            f"{'; '.join(kept)}. Some findings may be missing."
        ],
    }


def truncated_text_reason(dropped_chars: int, original_chars: int) -> list[str]:
    """Reason text for a letter that was cut to fit the prompt budget."""
    if dropped_chars <= 0:
        return []
    return [
        f"{dropped_chars:,} characters of the letter were not read "
        f"(it is {original_chars:,} characters long)"
    ]
