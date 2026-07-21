"""Convert heading-aware local guideline text into a reviewable draft.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from __future__ import annotations

import re

from app.schemas.local_guideline import (
    LocalChapterDraft,
    LocalGuidelineDraft,
    LocalGuidelineMetadata,
    LocalRecommendationDraft,
)
from app.services.local_guideline_chunker import chunk_by_heading

_NORMATIVE = re.compile(r"\b(offer|consider|refer|do not|should|must)\b", re.I)


def structure_local_guideline(
    metadata: LocalGuidelineMetadata, text: str
) -> LocalGuidelineDraft:
    """Build a deterministic draft for review before graph import."""
    chapters = [
        _structure_chunk(chunk, index)
        for index, chunk in enumerate(chunk_by_heading(text))
    ]
    chapters = [chapter for chapter in chapters if chapter.recommendations]
    errors = ["No normative recommendations found."] if not chapters else []
    return LocalGuidelineDraft(
        metadata=metadata,
        chapters=chapters,
        likely_incorrect=bool(errors),
        verification_errors=errors,
    )


def _structure_chunk(chunk: dict[str, str], order: int) -> LocalChapterDraft:
    """Extract imperative sentences from one heading section."""
    sentences = re.split(r"(?<=[.!?])\s+", chunk["text"])
    recommendations = [
        LocalRecommendationDraft(
            stable_key=f"{order + 1}.{index + 1}",
            title=chunk["title"],
            verbatim=sentence.strip(),
        )
        for index, sentence in enumerate(sentences)
        if _NORMATIVE.search(sentence)
    ]
    return LocalChapterDraft(
        title=chunk["title"], order=order, recommendations=recommendations
    )
