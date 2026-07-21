"""Build a local guideline shell for hand-authored rules (no pasted text).

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from __future__ import annotations

from app.schemas.local_guideline import (
    LocalChapterDraft,
    LocalGuidelineDraft,
    LocalGuidelineMetadata,
    LocalRecommendationDraft,
)


def build_blank_local_draft(metadata: LocalGuidelineMetadata) -> LocalGuidelineDraft:
    """Return a verified draft with one stub recommendation from the title.

    The title is used as recommendation verbatim so Build by hand has a
    normative recommendation without requiring pasted guideline text.
    """
    return LocalGuidelineDraft(
        metadata=metadata,
        chapters=[
            LocalChapterDraft(
                title="Manual rules",
                order=0,
                recommendations=[
                    LocalRecommendationDraft(
                        stable_key="manual-1",
                        title=metadata.title,
                        verbatim=metadata.title,
                        verification_flag=False,
                    )
                ],
            )
        ],
        likely_incorrect=False,
        verification_errors=[],
    )
