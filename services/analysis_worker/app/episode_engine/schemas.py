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

# Disruption / avoidable-delay categories. See R-LEO-AI-* (audit avoidable
# delays) and the NCDA "Avoidable Delays" section. Each category is mapped
# to an audit phase by the writer when the disruption date is compared to
# the episode milestones (before_presentation | pres_to_referral |
# after_referral).
DISRUPTION_CATEGORIES: tuple[str, ...] = (
    "referral_lost_or_not_received",
    "referral_rejected_or_returned",
    "repeat_referral_required",
    "appointment_dna",
    "appointment_cancelled_by_patient",
    "appointment_cancelled_by_trust",
    "result_not_received_in_primary_care",
    "letter_received_late",
    "patient_unreachable",
    "mdt_outcome_unclear",
    "other_administrative_delay",
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


class SafetyNetting(BaseModel):
    """Cancer safety-netting advice recorded in the source text.

    NCDA definition: documented advice to the patient about what
    symptoms should prompt re-presentation, when, and how (e.g.
    "advised to return if symptoms worsen / no improvement in 2
    weeks"). One entry per episode -- the EARLIEST documented advice
    on the pathway is the canonical record.
    """

    model_config = ConfigDict(extra="forbid")

    recorded: bool = False
    evidence_quote: Optional[str] = Field(
        default=None,
        description=(
            "Literal substring of the source encounter text that "
            "documents the safety-netting advice. Required when "
            "recorded == true."
        ),
    )
    encounter_id: Optional[str] = Field(
        default=None,
        description="Source encounter id; required when recorded == true.",
    )
    date: Optional[_date_t] = Field(
        default=None,
        description="Date the advice was given; required when recorded == true.",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Disruption(BaseModel):
    """A single avoidable-delay / pathway disruption event evidenced in the
    source text. The writer turns each entry into a (:Disruption) node
    attached to the EpisodeOfCare and rolls them up onto the episode
    properties used by the NCDA Avoidable Delays dashboard tile."""

    model_config = ConfigDict(extra="forbid")

    date: _date_t
    category: Literal[
        "referral_lost_or_not_received",
        "referral_rejected_or_returned",
        "repeat_referral_required",
        "appointment_dna",
        "appointment_cancelled_by_patient",
        "appointment_cancelled_by_trust",
        "result_not_received_in_primary_care",
        "letter_received_late",
        "patient_unreachable",
        "mdt_outcome_unclear",
        "other_administrative_delay",
    ]
    description: str = Field(
        ...,
        min_length=3,
        description="Plain-English one-liner; suitable for a clinician.",
    )
    encounter_id: str = Field(..., min_length=1)
    evidence_quote: str = Field(
        ...,
        min_length=3,
        description="Literal substring of the source encounter text.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)


class MilestoneExtractorResult(BaseModel):
    """Stage 4 output for one cancer/multi-site window."""

    model_config = ConfigDict(extra="forbid")

    window_id: str
    milestones: list[Milestone] = Field(default_factory=list)
    safety_netting: Optional[SafetyNetting] = Field(
        default=None,
        description=(
            "Cancer safety-netting advice for this window. Set "
            "recorded=false (or omit) when no advice is documented."
        ),
    )
    disruptions: list[Disruption] = Field(
        default_factory=list,
        description="Pathway disruptions / avoidable-delay events.",
    )
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
    safety_netting: Optional[SafetyNetting] = Field(
        default=None,
        description=(
            "Earliest documented safety-netting advice across the merged "
            "windows. Carried through verbatim from the extractor."
        ),
    )
    disruptions: list[Disruption] = Field(
        default_factory=list,
        description=(
            "Union of disruptions across merged windows, deduplicated by "
            "(date, category, encounter_id)."
        ),
    )
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
    safety_netting: Optional[SafetyNetting] = None
    disruptions: list[Disruption] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    needs_human_review: bool = False
    merged_from: list[str] = Field(default_factory=list)
    provenance: Provenance
