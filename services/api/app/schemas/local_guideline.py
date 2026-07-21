"""Request and draft schemas for locally curated guidelines.

Atlas trace:
  DO: DO-19FA25C3
  DI: DI-727C94B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-19FA25C3")
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LocalGuidelineMetadata(BaseModel):
    """Identity and display metadata supplied by an administrator."""

    short_code: str = Field(
        pattern=r"^[A-Z0-9][A-Z0-9-]{2,31}$",
        description="Stable upper-case local guideline identifier.",
    )
    title: str = Field(min_length=3, max_length=240)
    publication_date: str = ""
    version_label: str = ""


class LocalRecommendationDraft(BaseModel):
    """One recommendation extracted from local guideline text."""

    stable_key: str = Field(min_length=1, max_length=160)
    title: str = ""
    verbatim: str = Field(min_length=1)
    verification_flag: bool = False


class LocalChapterDraft(BaseModel):
    """A heading-derived chapter and its recommendations."""

    title: str = Field(min_length=1)
    order: int = Field(ge=0)
    recommendations: list[LocalRecommendationDraft] = Field(default_factory=list)


class LocalGuidelineDraft(BaseModel):
    """Structured local guideline ready for verification and import."""

    metadata: LocalGuidelineMetadata
    chapters: list[LocalChapterDraft] = Field(default_factory=list)
    likely_incorrect: bool = True
    verification_errors: list[str] = Field(default_factory=list)
