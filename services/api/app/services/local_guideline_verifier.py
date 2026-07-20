"""Fail-closed validation for local guideline structure drafts."""

from __future__ import annotations

from app.schemas.local_guideline import LocalGuidelineDraft


def verify_local_guideline(
    draft: LocalGuidelineDraft, source_text: str
) -> LocalGuidelineDraft:
    """Mark unsupported recommendations as unsafe to import."""
    errors = _verification_errors(draft, source_text)
    return draft.model_copy(
        update={
            "likely_incorrect": bool(errors),
            "verification_errors": errors,
        }
    )


def _verification_errors(draft: LocalGuidelineDraft, source_text: str) -> list[str]:
    """Return all missing-verbatim errors; empty means structurally verified."""
    errors: list[str] = []
    if not draft.chapters:
        errors.append("Draft has no recommendations.")
    source_lower = source_text.lower()
    for chapter in draft.chapters:
        for recommendation in chapter.recommendations:
            if recommendation.verbatim.lower() not in source_lower:
                errors.append(
                    f"Recommendation {recommendation.stable_key} is not in the source."
                )
    return errors
