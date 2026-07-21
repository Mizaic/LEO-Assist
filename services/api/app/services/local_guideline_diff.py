"""Small stable-key diff for local guideline re-import review.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from __future__ import annotations

from app.schemas.local_guideline import LocalGuidelineDraft


def diff_local_guidelines(
    previous: LocalGuidelineDraft, current: LocalGuidelineDraft
) -> dict[str, list[str]]:
    """Compare recommendations by their stable key and verbatim text."""
    before = _recommendations(previous)
    after = _recommendations(current)
    return {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "modified": sorted(
            key for key in before.keys() & after.keys() if before[key] != after[key]
        ),
    }


def _recommendations(draft: LocalGuidelineDraft) -> dict[str, str]:
    """Return a stable-key to verbatim map."""
    return {
        recommendation.stable_key: recommendation.verbatim
        for chapter in draft.chapters
        for recommendation in chapter.recommendations
    }
