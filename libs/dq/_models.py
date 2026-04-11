"""Pydantic response models shared across API, MCP, and CLI."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class SignalHit(BaseModel):
    date: str
    label: str
    snippet: str


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------


class CodedConcept(BaseModel):
    concept_id: str
    name: str
    assertion: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    semantic_tag: Optional[str] = None


class EncounterSummary(BaseModel):
    encounter_id: str
    date: str
    classification: Optional[str] = None
    coded_concepts: list[CodedConcept] = []
    text_preview: Optional[str] = None


class EpisodeSummary(BaseModel):
    episode_id: str
    site: str
    status: str
    referral_date: Optional[str] = None
    specialist_date: Optional[str] = None
    auto_closed: bool = False
    hitl_flag: bool = False
    hitl_reason: Optional[str] = None


class PatientSummary(BaseModel):
    patient_id: str
    encounter_count: int
    episode_count: int
    episodes: list[EpisodeSummary] = []
    encounters: list[EncounterSummary] = []


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


class EpisodeHealthResult(BaseModel):
    total_count: int
    status_counts: dict[str, int]
    stale_count: int
    hitl_count: int
    auto_closed_count: int


class StaleEpisode(BaseModel):
    patient_id: str
    episode_id: str
    site: str
    status: str
    days_stale: int
    referral_date: Optional[str] = None
    specialist_date: Optional[str] = None
    last_encounter_date: Optional[str] = None
    encounter_count: int = 0


class MilestoneRow(BaseModel):
    patient_id: str
    episode_id: str
    site: str
    status: str
    has_referral: bool
    has_specialist: bool
    has_diagnosis: bool
    has_treatment: bool
    has_letter: bool
    has_benign_closure: bool


class OutcomeInferenceResult(BaseModel):
    patient_id: str
    episode_id: str
    site: str
    referral_date: Optional[str] = None
    specialist_date: Optional[str] = None
    window_end: Optional[str] = None
    verdict: str
    flag: str
    cancer_signals: list[SignalHit] = []
    benign_signals: list[SignalHit] = []
    private_blocked: bool = False
    specialist_confirmed: bool = False
    phase2_encounter_count: int = 0


# ---------------------------------------------------------------------------
# Terminology
# ---------------------------------------------------------------------------


class MapsToEdge(BaseModel):
    concept_id: str
    preferred_term: Optional[str] = None
    score: float
    source: Optional[str] = None
    active: bool = True


class SurfaceFormDetail(BaseModel):
    normalized_term: str
    raw_form: Optional[str] = None
    maps_to: list[MapsToEdge] = []
    is_orphan: bool = False
    has_inactive_target: bool = False


class SurfaceFormAuditResult(BaseModel):
    total_count: int
    orphan_count: int
    duplicate_count: int
    inactive_target_count: int
    low_confidence_count: int
    anomalous_forms: list[SurfaceFormDetail] = []


class ResolveTestResult(BaseModel):
    term: str
    expected_concept_id: Optional[str] = None
    resolved_concept_id: Optional[str] = None
    resolved_term: Optional[str] = None
    score: Optional[float] = None
    status: str  # pass | fail | error


class PinVerifyResult(BaseModel):
    phrase: str
    concept_id: str
    kg_edge_exists: bool
    http_resolves: bool
    status: str  # pass | fail


class ConceptStatus(BaseModel):
    concept_id: str
    preferred_term: Optional[str] = None
    active: bool
    semantic_tag: Optional[str] = None
    replacement_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Coding quality
# ---------------------------------------------------------------------------


class CodingIssueSummary(BaseModel):
    total_assessed: int
    clean_count: int
    has_issues_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    top_missing: list[dict[str, Any]] = []


class CodingIssueRow(BaseModel):
    encounter_id: str
    patient_id: Optional[str] = None
    date: Optional[str] = None
    assessment: str
    missing_critical: int = 0
    missing_high: int = 0
    overcoded: int = 0
    wrong_assertion: int = 0


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class OrphanConcept(BaseModel):
    concept_id: str
    preferred_term: Optional[str] = None
    active: bool = False
    replacement_id: Optional[str] = None
    patient_count: int = 0


class PathwayGap(BaseModel):
    patient_id: str
    episode_id: Optional[str] = None
    site: str
    gap_type: (
        str  # referral_no_diagnosis | diagnosis_no_referral | treatment_no_episode
    )
    date: Optional[str] = None
    days_since: Optional[int] = None


class DomainCoverageResult(BaseModel):
    domain_id: str
    total_concepts_in_valueset: int
    encounter_concepts_not_in_valueset: int
    orphan_concepts: list[OrphanConcept] = []
    pathway_gaps: list[PathwayGap] = []


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------


class RemediationResult(BaseModel):
    operation: str
    dry_run: bool
    affected_count: int
    affected_items: list[dict[str, Any]] = []
    message: str


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class SitrepResult(BaseModel):
    episode_status_counts: dict[str, int]
    stale_count: int
    hitl_queue_depth: int
    sf_task_backlog: int
    gold_label_count: int
    training_candidate_count: int
    last_dq_run: Optional[str] = None


class CohortResult(BaseModel):
    patient_ids: list[str]
    total_count: int
    filters_applied: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# DQ Rules Engine
# ---------------------------------------------------------------------------


class DQCheckResult(BaseModel):
    rule_id: str
    dimension: str
    severity: str  # critical | high | medium | low
    status: str  # pass | warn | fail
    violation_count: int
    threshold: int
    sample_violations: list[dict[str, Any]] = []
    description: str
