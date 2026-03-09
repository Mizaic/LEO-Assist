"""Shared state definitions for pipeline subgraphs.

Each subgraph defines its own state TypedDict.  These shared types are
used when subgraphs need to communicate through a parent graph.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class EncounterContext(TypedDict, total=False):
    """Core patient/encounter context that flows through the pipeline."""
    patient_id: str
    encounter_id: str
    encounter_text: str
    encounter_date: str
    classification: str
    org_id: str


class PipelineConfig(TypedDict, total=False):
    """Configuration for a pipeline run, derived from ActivityDefinition."""
    extraction_method: Literal["llm", "ner", "auto"]
    output_target: Literal["patient_graph", "gold_training", "both"]
    verify: bool
    verify_model_tier: Literal["big", "small"]
    post_processing_layers: list[str] | None
    prompt_config_id: str
    coding_mode: Literal["hitl", "autonomous"]


class ExtractionState(TypedDict, total=False):
    """State for extraction subgraphs."""
    encounter_text: str
    extraction_method: str
    prompt_config: dict[str, Any]
    sentences: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    errors: list[str]


class PostProcessingState(TypedDict, total=False):
    """State for post-processing subgraph."""
    encounter_text: str
    entities: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    enable_disorder_gate: bool
    coding_mode: str
    processed_entities: list[dict[str, Any]]
    post_processing_trace: list[dict[str, Any]]


class TerminologyState(TypedDict, total=False):
    """State for terminology resolution subgraph."""
    entities: list[dict[str, Any]]
    expected_tags: dict[str, str]
    resolved_entities: list[dict[str, Any]]


class TierClassifyState(TypedDict, total=False):
    """State for tier classification subgraph."""
    entities: list[dict[str, Any]]
    coding_mode: str
    tier_decisions: list[dict[str, Any]]


class VerificationState(TypedDict, total=False):
    """State for the verification subgraph (extract-verify-retry loop)."""
    encounter_text: str
    entities: list[dict[str, Any]]
    prompt_config: dict[str, Any]
    model_tier: str
    max_retries: int
    confidence_threshold: float
    extraction_attempts: list[dict[str, Any]]
    verification_result: dict[str, Any]
    is_verified: bool


class PersistState(TypedDict, total=False):
    """State for persistence subgraph."""
    patient_id: str
    encounter_id: str
    entities: list[dict[str, Any]]
    tier_decisions: list[dict[str, Any]]
    output_target: str
    documents_written: int
    training_labels_written: int


class AnalyticsState(TypedDict, total=False):
    """State for analytics subgraphs (episode, safety net, quality, etc.)."""
    patient_id: str
    org_id: str
    analytics_config: list[str]
    anchors: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    safety_net_alerts: list[dict[str, Any]]
    quality_issues: list[dict[str, Any]]
    kpis: dict[str, Any]


class SBARState(TypedDict, total=False):
    """State for SBAR generation subgraph."""
    patient_id: str
    referral_id: str
    patient_context: list[dict[str, Any]]
    prompt_configs: list[dict[str, Any]]
    sbar_sections: dict[str, str]
    extracted: list[dict[str, Any]]


class ComplianceState(TypedDict, total=False):
    """State for compliance evaluation subgraph."""
    patient_id: str
    checklist: dict[str, Any]
    compliance_report: dict[str, Any]
    extracted: list[dict[str, Any]]


class PipelineState(TypedDict, total=False):
    """Top-level orchestration state for the pipeline worker."""
    # Input
    patient_id: str
    encounter_id: str | None
    event_type: str
    plan_definition_id: str
    context: dict[str, Any]

    # Config (from ActivityDefinition)
    config: PipelineConfig

    # Pipeline data
    encounter: EncounterContext
    sentences: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    resolved_entities: list[dict[str, Any]]
    tier_decisions: list[dict[str, Any]]

    # Output
    documents_written: int
    training_labels_written: int
    verification_result: dict[str, Any] | None
    analytics_results: dict[str, Any]

    # Metadata
    run_id: str
    errors: list[str]
    checkpoints: list[str]
