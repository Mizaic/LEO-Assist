"""UN-scoped validation workflow definitions.

Atlas trace:
  UN: UN-89E2AE36, UN-5F3BF083, UN-AF530E8E, UN-CBF42476, UN-F8819A42
  VAL: VAL-87173594

These PlanDefinitions are validation and orchestration entry points. They reuse
the production subgraphs but stop at the user-need boundary that each VAL needs.

Extraction routing
------------------
Validation plans use ``ad-extraction-referral`` (LLM-only, Haiku via
``PIPELINE_MODEL_TIER``). The workflow engine also applies
``apply_single_model_defaults()`` so validation runs do not use NER auto-routing
or dual-model LLM judges. Per-run ``context.model_mode`` overrides are still
honoured when set explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_DURABLE_VERSION_ROLLOUT: dict[str, Any] = {
    "defaultVersion": "latest",
    "canaryVersion": "",
    "canaryOrgAllowlist": [],
    "canaryPercent": 0,
    "rollbackTarget": "",
}


def _durable_plan_meta() -> dict[str, Any]:
    return {
        "_workflowMode": "durable_pubsub",
        "_versionRollout": dict(_DURABLE_VERSION_ROLLOUT),
    }


@dataclass(frozen=True)
class ValidationWorkflowSpec:
    un_id: str
    val_id: str
    plan_definition_id: str
    metric: str
    output_contract: tuple[str, ...]


def _action(
    action_id: str,
    title: str,
    sequence: int,
    subgraph_id: str,
    definition: str,
    *,
    trigger: str | None = None,
    after: str | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "id": action_id,
        "title": title,
        "_sequence": sequence,
        "_subgraphId": subgraph_id,
        "definitionCanonical": f"ActivityDefinition/{definition}",
    }
    if trigger:
        action["trigger"] = [{"type": "data-changed", "name": trigger}]
    if after:
        action["relatedAction"] = [{"actionId": after, "relationship": "after-end"}]
    return action


VALIDATION_WORKFLOW_SPECS: dict[str, ValidationWorkflowSpec] = {
    "UN-89E2AE36": ValidationWorkflowSpec(
        un_id="UN-89E2AE36",
        val_id="VAL-87173594",
        plan_definition_id="pd-val-key-fact-extraction",
        metric="phrase_level_f1",
        output_contract=(
            "case_id",
            "terms[].text",
            "missed_strings",
            "extra_strings",
            "precision",
            "recall",
            "f1",
        ),
    ),
    "UN-5F3BF083": ValidationWorkflowSpec(
        un_id="UN-5F3BF083",
        val_id="VAL-pathway-criteria",
        plan_definition_id="pd-val-pathway-criteria",
        metric="criteria_suitability_accuracy",
        output_contract=(
            "case_id",
            "pathway_id",
            "suitability",
            "matched_criteria",
            "failed_criteria",
            "needs_review_reason",
        ),
    ),
    "UN-AF530E8E": ValidationWorkflowSpec(
        un_id="UN-AF530E8E",
        val_id="VAL-triage-completeness",
        plan_definition_id="pd-val-triage-completeness",
        metric="required_field_recall",
        output_contract=(
            "case_id",
            "required_fields",
            "present_fields",
            "missing_fields",
            "unclear_fields",
        ),
    ),
    "UN-CBF42476": ValidationWorkflowSpec(
        un_id="UN-CBF42476",
        val_id="VAL-terminology-mapping",
        plan_definition_id="pd-val-terminology-mapping",
        metric="concept_mapping_accuracy",
        output_contract=(
            "case_id",
            "source_text",
            "concept_id",
            "preferred_term",
            "semantic_tag",
            "confidence",
            "resolution_status",
        ),
    ),
    "UN-F8819A42": ValidationWorkflowSpec(
        un_id="UN-F8819A42",
        val_id="VAL-sbar-summary",
        plan_definition_id="pd-val-sbar-summary",
        metric="sbar_section_completeness",
        output_contract=(
            "case_id",
            "sbar_sections",
            "source_references",
            "unsupported_claims",
            "completion_status",
        ),
    ),
}


VALIDATION_PLAN_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "pd-val-key-fact-extraction",
        "resourceType": "PlanDefinition",
        "name": "VAL Key Fact Extraction",
        "status": "active",
        "description": (
            "Validation workflow for UN-89E2AE36: run extraction, shared "
            "pre-coding post-processing, relation linking, and extraction "
            "quality check to mirror pd-gp-encounter-coding up to the "
            "extraction boundary."
        ),
        **_durable_plan_meta(),
        "action": [
            _action(
                "act-val-extract",
                "Extract Key Facts",
                0,
                "extraction",
                "ad-extraction-referral",
                trigger="validation-run-requested",
            ),
            _action(
                "act-val-post",
                "Post-Process",
                1,
                "post_processing",
                "ad-post-processing",
                after="act-val-extract",
            ),
            _action(
                "act-val-relation-link",
                "Link Entity Relations",
                2,
                "relation_linking",
                "ad-relation-linking",
                after="act-val-post",
            ),
            _action(
                "act-val-extraction-check",
                "Extraction Quality Check",
                3,
                "extraction_check",
                "ad-extraction-check",
                after="act-val-relation-link",
            ),
        ],
    },
    {
        "id": "pd-val-pathway-criteria",
        "resourceType": "PlanDefinition",
        "name": "VAL Pathway Criteria Suitability",
        "status": "active",
        "description": "Validation workflow for UN-5F3BF083: map referral reason and assess pathway criteria.",
        **_durable_plan_meta(),
        "action": [
            _action(
                "act-val-criteria-extract",
                "Extract Referral Facts",
                0,
                "extraction",
                "ad-extraction-referral",
                trigger="validation-run-requested",
            ),
            _action(
                "act-val-criteria-post",
                "Post-Process",
                1,
                "post_processing",
                "ad-post-processing",
                after="act-val-criteria-extract",
            ),
            _action(
                "act-val-criteria-relation-link",
                "Link Entity Relations",
                2,
                "relation_linking",
                "ad-relation-linking",
                after="act-val-criteria-post",
            ),
            _action(
                "act-val-criteria-extraction-check",
                "Extraction Quality Check",
                3,
                "extraction_check",
                "ad-extraction-check",
                after="act-val-criteria-relation-link",
            ),
            _action(
                "act-val-criteria-terminology",
                "Resolve Terminology",
                4,
                "terminology",
                "ad-terminology",
                after="act-val-criteria-extraction-check",
            ),
            _action(
                "act-val-criteria-compliance",
                "Assess Criteria",
                5,
                "compliance",
                "ad-compliance",
                after="act-val-criteria-terminology",
            ),
        ],
    },
    {
        "id": "pd-val-triage-completeness",
        "resourceType": "PlanDefinition",
        "name": "VAL Triage Completeness",
        "status": "active",
        "description": "Validation workflow for UN-AF530E8E: extract referral facts and assess missing or unclear triage information.",
        **_durable_plan_meta(),
        "action": [
            _action(
                "act-val-complete-extract",
                "Extract Triage Facts",
                0,
                "extraction",
                "ad-extraction-referral",
                trigger="validation-run-requested",
            ),
            _action(
                "act-val-complete-post",
                "Post-Process",
                1,
                "post_processing",
                "ad-post-processing",
                after="act-val-complete-extract",
            ),
            _action(
                "act-val-complete-relation-link",
                "Link Entity Relations",
                2,
                "relation_linking",
                "ad-relation-linking",
                after="act-val-complete-post",
            ),
            _action(
                "act-val-complete-extraction-check",
                "Extraction Quality Check",
                3,
                "extraction_check",
                "ad-extraction-check",
                after="act-val-complete-relation-link",
            ),
            _action(
                "act-val-complete-quality",
                "Assess Completeness",
                4,
                "quality_check",
                "ad-quality-check",
                after="act-val-complete-extraction-check",
            ),
        ],
    },
    {
        "id": "pd-val-terminology-mapping",
        "resourceType": "PlanDefinition",
        "name": "VAL Terminology Mapping",
        "status": "active",
        "description": "Validation workflow for UN-CBF42476: map extracted facts to recognised clinical terminology.",
        **_durable_plan_meta(),
        "action": [
            _action(
                "act-val-term-extract",
                "Extract Facts",
                0,
                "extraction",
                "ad-extraction-referral",
                trigger="validation-run-requested",
            ),
            _action(
                "act-val-term-post",
                "Post-Process",
                1,
                "post_processing",
                "ad-post-processing",
                after="act-val-term-extract",
            ),
            _action(
                "act-val-term-relation-link",
                "Link Entity Relations",
                2,
                "relation_linking",
                "ad-relation-linking",
                after="act-val-term-post",
            ),
            _action(
                "act-val-term-extraction-check",
                "Extraction Quality Check",
                3,
                "extraction_check",
                "ad-extraction-check",
                after="act-val-term-relation-link",
            ),
            _action(
                "act-val-term-resolve",
                "Resolve Terminology",
                4,
                "terminology",
                "ad-terminology",
                after="act-val-term-extraction-check",
            ),
            _action(
                "act-val-term-surface",
                "Validate Surface Forms",
                5,
                "surface_form_validation",
                "ad-surface-form-validation",
                after="act-val-term-resolve",
            ),
        ],
    },
    {
        "id": "pd-val-sbar-summary",
        "resourceType": "PlanDefinition",
        "name": "VAL SBAR Summary",
        "status": "active",
        "description": "Validation workflow for UN-F8819A42: generate a grounded SBAR summary from referral facts.",
        **_durable_plan_meta(),
        "action": [
            _action(
                "act-val-sbar-extract",
                "Extract Facts",
                0,
                "extraction",
                "ad-extraction-referral",
                trigger="validation-run-requested",
            ),
            _action(
                "act-val-sbar-post",
                "Post-Process",
                1,
                "post_processing",
                "ad-post-processing",
                after="act-val-sbar-extract",
            ),
            _action(
                "act-val-sbar-relation-link",
                "Link Entity Relations",
                2,
                "relation_linking",
                "ad-relation-linking",
                after="act-val-sbar-post",
            ),
            _action(
                "act-val-sbar-extraction-check",
                "Extraction Quality Check",
                3,
                "extraction_check",
                "ad-extraction-check",
                after="act-val-sbar-relation-link",
            ),
            _action(
                "act-val-sbar-terminology",
                "Resolve Terminology",
                4,
                "terminology",
                "ad-terminology",
                after="act-val-sbar-extraction-check",
            ),
            _action(
                "act-val-sbar-generate",
                "Generate SBAR",
                5,
                "sbar",
                "ad-sbar",
                after="act-val-sbar-terminology",
            ),
        ],
    },
]


REFERRAL_TRIAGE_PLAN_DEFINITION: dict[str, Any] = {
    "id": "pd-referral-triage-e2e",
    "resourceType": "PlanDefinition",
    "name": "Referral Triage End to End",
    "status": "active",
    "description": "End-to-end referral triage workflow composed from UN-scoped stages.",
    **_durable_plan_meta(),
    "action": [
        _action(
            "act-triage-extract",
            "Extract Key Facts",
            0,
            "extraction",
            "ad-extraction-referral",
            trigger="referral-triage-requested",
        ),
        _action(
            "act-triage-post",
            "Post-Process",
            1,
            "post_processing",
            "ad-post-processing",
            after="act-triage-extract",
        ),
        _action(
            "act-triage-relation-link",
            "Link Entity Relations",
            2,
            "relation_linking",
            "ad-relation-linking",
            after="act-triage-post",
        ),
        _action(
            "act-triage-extraction-check",
            "Extraction Quality Check",
            3,
            "extraction_check",
            "ad-extraction-check",
            after="act-triage-relation-link",
        ),
        _action(
            "act-triage-terminology",
            "Map Terminology",
            4,
            "terminology",
            "ad-terminology",
            after="act-triage-extraction-check",
        ),
        _action(
            "act-triage-criteria",
            "Assess Pathway Criteria",
            5,
            "compliance",
            "ad-compliance",
            after="act-triage-terminology",
        ),
        _action(
            "act-triage-completeness",
            "Assess Completeness",
            6,
            "quality_check",
            "ad-quality-check",
            after="act-triage-criteria",
        ),
        _action(
            "act-triage-sbar",
            "Generate SBAR",
            7,
            "sbar",
            "ad-sbar",
            after="act-triage-completeness",
        ),
        _action(
            "act-triage-review",
            "Pause For Human Review",
            8,
            "human_review_gate",
            "ad-human-review-gate",
            after="act-triage-sbar",
        ),
    ],
}


def get_validation_spec(un_id: str) -> ValidationWorkflowSpec:
    try:
        return VALIDATION_WORKFLOW_SPECS[un_id]
    except KeyError as exc:
        raise KeyError(f"No validation workflow configured for {un_id}") from exc


def all_validation_plan_definitions() -> list[dict[str, Any]]:
    return [*VALIDATION_PLAN_DEFINITIONS, REFERRAL_TRIAGE_PLAN_DEFINITION]
