"""Shared API and pipeline contracts for HITL training creator MVP."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReviewStatus(str, Enum):
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    escalated = "escalated"


class ReviewAction(str, Enum):
    approve = "approve"
    edit = "edit"
    reject = "reject"
    escalate = "escalate"


class ContextSubject(str, Enum):
    patient = "patient"
    family = "family"
    other = "other"


class Temporality(str, Enum):
    present = "present"
    past = "past"
    planned = "planned"
    hypothetical = "hypothetical"
    unknown = "unknown"


class TermContext(BaseModel):
    negated: bool
    uncertain: bool
    historical: bool
    subject: ContextSubject
    temporality: Temporality


class TermCodingProposal(BaseModel):
    snomed_concept_id: str | None = None
    read_code: str | None = None
    snomed_term: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="neo4j_hybrid")


class EncounterTerm(BaseModel):
    term_id: str
    text: str
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    context: TermContext
    coding: TermCodingProposal
    evidence_text: str
    extraction_method: str
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("span_end")
    @classmethod
    def validate_spans(cls, span_end: int, info):  # type: ignore[override]
        start = info.data.get("span_start", 0)
        if span_end <= start:
            raise ValueError("span_end must be greater than span_start")
        return span_end


class EncounterSentence(BaseModel):
    sentence_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str
    section: str | None = None
    terms: list[EncounterTerm]

    @field_validator("end")
    @classmethod
    def validate_sentence_span(cls, end: int, info):  # type: ignore[override]
        start = info.data.get("start", 0)
        if end <= start:
            raise ValueError("sentence end must be greater than start")
        return end


class VersionBundle(BaseModel):
    pipeline_version: str
    extractor_version: str
    validator_version: str
    model_id: str
    prompt_version: str
    terminology_version: str


class ChangeEvent(BaseModel):
    event_type: str
    actor: str
    reason: str
    timestamp: datetime
    before_hash: str
    after_hash: str
    version_bundle: VersionBundle


class EncounterCandidate(BaseModel):
    candidate_id: str
    patient_id: str
    encounter_id: str
    date: str
    source_hash: str
    deidentified_hash: str
    deidentified_text: str
    approval_status: ReviewStatus = ReviewStatus.pending
    hard_fail_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    sentences: list[EncounterSentence]
    audit_events: list[ChangeEvent] = Field(default_factory=list)


class PipelineRunRequest(BaseModel):
    patient_ids: list[str] = Field(min_length=1)
    max_encounters_per_patient: int | None = Field(default=None, gt=0)
    dry_run: bool = False


class PipelineRunResponse(BaseModel):
    run_id: str
    processed_encounters: int
    queued_for_review: int
    rejected_hard_fail: int
    warnings_only: int


class ReviewTaskSummary(BaseModel):
    task_id: str
    candidate_id: str
    patient_id: str
    encounter_id: str
    priority: int
    status: ReviewStatus
    warning_count: int
    created_at: datetime
    updated_at: datetime


class ReviewTaskDetail(BaseModel):
    task: ReviewTaskSummary
    candidate: EncounterCandidate


class ReviewDecisionRequest(BaseModel):
    action: ReviewAction
    reviewer: str
    reason: str = Field(min_length=3)
    edited_candidate: dict[str, Any] | None = None

    @field_validator("edited_candidate")
    @classmethod
    def validate_edit_payload(cls, edited_candidate: dict[str, Any] | None, info):  # type: ignore[override]
        action = info.data.get("action")
        if action == ReviewAction.edit and edited_candidate is None:
            raise ValueError("edited_candidate is required for edit actions")
        return edited_candidate


class ReviewDecisionResponse(BaseModel):
    task_id: str
    candidate_id: str
    status: ReviewStatus
    approval_event_id: str


class AuditTimelineResponse(BaseModel):
    candidate_id: str
    changes: list[dict[str, Any]]
    approvals: list[dict[str, Any]]


class ExportDatasetRequest(BaseModel):
    export_name: str = Field(min_length=3)
    train_ratio: float = Field(default=0.8, gt=0.0, lt=1.0)
    random_seed: int = Field(default=42, ge=0)


class ExportDatasetResponse(BaseModel):
    export_id: str
    approved_rows: int
    train_rows: int
    validation_rows: int
    manifest: dict[str, Any]


class ExportMedSpaCyRequest(BaseModel):
    export_name: str = Field(min_length=3)
    patient_ids: list[str] | None = Field(default=None, description="Limit to these patients; omit for all")


class ExportMedSpaCyResponse(BaseModel):
    export_id: str
    entity_count: int
    kb_count: int
    encounter_count: int
    export_path: str | None = None
