"""Pydantic schemas for the Haiku episode engine.

These models define the contract between every chain stage. They double as
the JSON Schema fed to Bedrock ``tool_config`` so the model is forced to
return structurally-valid output.

Keep these schemas SMALL. Every field added here costs LLM tokens at every
stage and increases the surface for hallucination.
"""

from __future__ import annotations

from datetime import date as _date_t
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# -- Vocabularies -----------------------------------------------------------
# Kept here, not on the model, so the prompts can import the same
# vocabularies as the schemas. Drift between the prompt and the schema is
# the most common cause of dropped LLM responses.

MILESTONE_TYPES: tuple[str, ...] = (
    "first_presentation",
    "referral",
    "first_seen",
    "outcome_letter",
    "diagnosis_confirmed",
    "treatment_started",
    "treatment_completed",
    "benign_closure",
)

EPISODE_TYPES: tuple[str, ...] = (
    "cancer",
    "multi_site",
    "benign",
    "non_cancer",
    "uncertain",
)

TREATMENT_TYPES: tuple[str, ...] = (
    "surgery",
    "endocrine",
    "chemotherapy",
    "radiotherapy",
    "immunotherapy",
    "other",
)

# Place of first presentation -- mirrors the NCDA cancer audit dropdown.
# Used only when type == "first_presentation".
PRESENTATION_PLACES: tuple[str, ...] = (
    "gp_surgery",
    "gp_home_visit",
    "other_primary_care",
    "hospital_outpatient",
    "hospital_inpatient",
    "accident_and_emergency",
    "walk_in_centre",
    "out_of_hours",
    "from_screening",
    "telephone_consultation",
    "email_consultation",
    "video_consultation",
    "dentist",
    "optometrist",
    "community_care_nurse",
    "other",
    "not_known",
)


# -- Stage outputs ----------------------------------------------------------


class CandidateWindow(BaseModel):
    """Output of stage 2 (segmenter): one row per candidate episode window."""

    model_config = ConfigDict(extra="forbid")

    window_id: str = Field(..., description="Stable id within the call: w1, w2, ...")
    suspected_site: str = Field(..., description="Free-text body site or 'unknown'.")
    window_start: _date_t
    window_end: Optional[_date_t] = None
    rationale: str = Field(..., description="One-sentence reason for the window.")


class SegmenterResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    windows: list[CandidateWindow] = Field(default_factory=list)
    notes: str = ""


class ClassifierResult(BaseModel):
    """Stage 3 output for one window."""

    model_config = ConfigDict(extra="forbid")

    window_id: str
    episode_type: Literal["cancer", "multi_site", "benign", "non_cancer", "uncertain"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "first_presentation",
        "referral",
        "first_seen",
        "outcome_letter",
        "diagnosis_confirmed",
        "treatment_started",
        "treatment_completed",
        "benign_closure",
    ]
    date: _date_t
    encounter_id: str = Field(..., min_length=1)
    evidence_quote: str = Field(
        ...,
        min_length=3,
        description="Substring of the source encounter text proving the milestone.",
    )
    treatment_type: Optional[
        Literal[
            "surgery",
            "endocrine",
            "chemotherapy",
            "radiotherapy",
            "immunotherapy",
            "other",
        ]
    ] = None
    presentation_place: Optional[
        Literal[
            "gp_surgery",
            "gp_home_visit",
            "other_primary_care",
            "hospital_outpatient",
            "hospital_inpatient",
            "accident_and_emergency",
            "walk_in_centre",
            "out_of_hours",
            "from_screening",
            "telephone_consultation",
            "email_consultation",
            "video_consultation",
            "dentist",
            "optometrist",
            "community_care_nurse",
            "other",
            "not_known",
        ]
    ] = Field(
        default=None,
        description=(
            "Where the patient first presented, from the NCDA dropdown. "
            "Only set when type == 'first_presentation'. Use 'not_known' "
            "if presentation place cannot be inferred from the source text."
        ),
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class MilestoneExtractorResult(BaseModel):
    """Stage 4 output for one cancer/multi-site window."""

    model_config = ConfigDict(extra="forbid")

    window_id: str
    milestones: list[Milestone] = Field(default_factory=list)
    needs_human_review: bool = False
    reasoning: str = ""


class ReconciledEpisode(BaseModel):
    """Stage 5 output: an episode after merging/splitting."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    suspected_site: str
    episode_type: Literal["cancer", "multi_site", "benign", "non_cancer", "uncertain"]
    window_start: _date_t
    window_end: Optional[_date_t] = None
    milestones: list[Milestone] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    needs_human_review: bool = False
    merged_from: list[str] = Field(
        default_factory=list,
        description="window_ids of input windows merged into this episode.",
    )


class ReconcilerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodes: list[ReconciledEpisode] = Field(default_factory=list)
    notes: str = ""


# -- Provenance + final episode ---------------------------------------------


class StageTrace(BaseModel):
    """One row of provenance per stage call."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    prompt_version: str
    model_id: str
    tier: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    ok: bool = True
    error: str = ""


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    stages: list[StageTrace] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_input_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    timeline_encounter_count: int = 0


class Episode(BaseModel):
    """Final episode shape written to Neo4j."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str = Field(..., description="Deterministic hash of patient + window.")
    patient_id: str
    suspected_site: str
    episode_type: Literal["cancer", "multi_site", "benign", "non_cancer", "uncertain"]
    window_start: _date_t
    window_end: Optional[_date_t] = None
    milestones: list[Milestone] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    needs_human_review: bool = False
    merged_from: list[str] = Field(default_factory=list)
    provenance: Provenance
