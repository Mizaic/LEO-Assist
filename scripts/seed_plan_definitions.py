"""Seed the three core PlanDefinitions and their ActivityDefinitions into Neo4j.

Usage:
    python -m scripts.seed_plan_definitions

Idempotent — uses MERGE on node IDs.

PlanDefinitions:
  1. gp-encounter-coding   — Primary care encounter NER extraction pipeline
  2. referral-assessment    — Referral document SBAR generation pipeline
  3. gold-training-audit    — Gold-standard NER training data pipeline

Each PlanDefinition has a sequence of Actions that reference ActivityDefinitions.
ActivityDefinitions map to subgraph IDs in the SubgraphRegistry.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_ROOT = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv

load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
from libs.workflow.validation_workflows import all_validation_plan_definitions

try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


ACTIVITY_DEFINITIONS = [
    {
        "id": "ad-encounter-loader",
        "resourceType": "ActivityDefinition",
        "name": "Encounter Text Loader",
        "status": "active",
        "description": "Load encounter clinical text from Neo4j patient graph",
        "_subgraphId": "encounter_loader",
    },
    {
        "id": "ad-extraction-llm",
        "resourceType": "ActivityDefinition",
        "name": "LLM Entity Extraction",
        "status": "active",
        "description": "Extract clinical entities from encounter text using LLM",
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "llm"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {"path": "prompt_config_name", "expression": {"expression": "extraction"}},
            {"path": "prompt_config_version", "expression": {"expression": "1"}},
        ],
    },
    {
        "id": "ad-extraction-referral",
        "resourceType": "ActivityDefinition",
        "name": "Referral LLM Entity Extraction",
        "status": "active",
        "description": "Extract referral-focused clinical entities using dedicated prompt",
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "llm"}},
            {"path": "model_mode", "expression": {"expression": "llm"}},
            {"path": "model_tier", "expression": {"expression": "small"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {
                "path": "prompt_config_name",
                "expression": {"expression": "referral_extraction"},
            },
            {"path": "prompt_config_version", "expression": {"expression": "1"}},
        ],
    },
    {
        "id": "ad-extraction-ner",
        "resourceType": "ActivityDefinition",
        "name": "NER Model Entity Extraction",
        "status": "active",
        "description": "Extract clinical entities from encounter text using trained NER model",
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "ner"}},
        ],
    },
    {
        "id": "ad-extraction-auto",
        "resourceType": "ActivityDefinition",
        "name": "Auto Entity Extraction (NER -> LLM fallback)",
        "status": "active",
        "description": (
            "Prefer trained NER when MODEL_MODE_NER_ENABLED is on and the "
            "backend is reachable; fall back to the LLM extractor otherwise. "
            "Per-request override via pub/sub payload context.model_mode."
        ),
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "auto"}},
            {"path": "model_mode", "expression": {"expression": "auto"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {"path": "prompt_config_name", "expression": {"expression": "extraction"}},
            {"path": "prompt_config_version", "expression": {"expression": "1"}},
        ],
    },
    {
        "id": "ad-extraction-auto-referral",
        "resourceType": "ActivityDefinition",
        "name": "Auto Referral Entity Extraction (NER -> referral LLM fallback)",
        "status": "active",
        "description": (
            "Validation-side auto extraction that mirrors ad-extraction-auto "
            "but binds the referral prompt for LLM fallback. Used by "
            "pd-val-* PlanDefinitions so validation tracks the production "
            "routing while the NER model is being trained."
        ),
        "_subgraphId": "extraction",
        "dynamicValue": [
            {"path": "extraction_method", "expression": {"expression": "auto"}},
            {"path": "model_mode", "expression": {"expression": "auto"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {
                "path": "prompt_config_name",
                "expression": {"expression": "referral_extraction"},
            },
            {"path": "prompt_config_version", "expression": {"expression": "1"}},
        ],
    },
    {
        "id": "ad-post-processing",
        "resourceType": "ActivityDefinition",
        "name": "Post-Processing Pipeline",
        "status": "active",
        "description": "9-layer post-processing: dedup, negation gate, disorder gate, etc.",
        "_subgraphId": "post_processing",
        "dynamicValue": [
            {"path": "coding_mode", "expression": {"expression": "hitl"}},
            {"path": "enable_disorder_gate", "expression": {"expression": True}},
        ],
    },
    {
        "id": "ad-relation-linking",
        "resourceType": "ActivityDefinition",
        "name": "Relation Linking",
        "status": "active",
        "description": "Single-turn LLM relation linking for body site and qualifier relations",
        "_subgraphId": "relation_linking",
        "dynamicValue": [
            {"path": "model_tier", "expression": {"expression": "small"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {
                "path": "prompt_config_name",
                "expression": {"expression": "relation_linking"},
            },
            {"path": "prompt_config_version", "expression": {"expression": "1"}},
        ],
    },
    {
        "id": "ad-condition-extraction-route",
        "resourceType": "ActivityDefinition",
        "name": "Route After Extraction Check",
        "status": "active",
        "description": "Condition node that routes extraction changes to HITL queue",
        "_subgraphId": "condition",
        "dynamicValue": [
            {
                "path": "rules",
                "expression": {
                    "expression": [
                        {
                            "field": "has_extraction_changes",
                            "operator": "==",
                            "value": True,
                            "outputPort": "changed",
                        }
                    ]
                },
            },
            {"path": "defaultPort", "expression": {"expression": "pass_through"}},
        ],
    },
    {
        "id": "ad-hitl-ner-queue",
        "resourceType": "ActivityDefinition",
        "name": "Queue NER HITL Review",
        "status": "active",
        "description": "Writes extraction-change training candidates with HITL guidance",
        "_subgraphId": "hitl_ner_queue",
    },
    {
        "id": "ad-terminology",
        "resourceType": "ActivityDefinition",
        "name": "Terminology Resolution",
        "status": "active",
        "description": "Resolve extracted entities to SNOMED CT codes via terminology API",
        "_subgraphId": "terminology",
    },
    {
        "id": "ad-tier-classify",
        "resourceType": "ActivityDefinition",
        "name": "Tier Classification",
        "status": "active",
        "description": "Three-tier confidence classification for HITL routing",
        "_subgraphId": "tier_classify",
        "dynamicValue": [
            {"path": "coding_mode", "expression": {"expression": "hitl"}},
        ],
    },
    {
        "id": "ad-verification",
        "resourceType": "ActivityDefinition",
        "name": "Big-Model Verification",
        "status": "active",
        "description": "Verify extraction quality using a larger LLM with retry loop",
        "_subgraphId": "verification",
        "dynamicValue": [
            {"path": "model_tier", "expression": {"expression": "big"}},
            {"path": "max_retries", "expression": {"expression": "2"}},
            {"path": "confidence_threshold", "expression": {"expression": "0.8"}},
        ],
    },
    {
        "id": "ad-extraction-check",
        "resourceType": "ActivityDefinition",
        "name": "Extraction Quality Check",
        "status": "active",
        "description": "Single-turn LLM quality check for extraction-level fixes",
        "_subgraphId": "extraction_check",
        "dynamicValue": [
            {"path": "model_tier", "expression": {"expression": "small"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {
                "path": "prompt_config_name",
                "expression": {"expression": "extraction_check"},
            },
            {"path": "prompt_config_version", "expression": {"expression": "2"}},
        ],
    },
    {
        "id": "ad-coding-check",
        "resourceType": "ActivityDefinition",
        "name": "Coding Quality Check",
        "status": "active",
        "description": "Single-turn LLM quality check for coded entity plausibility",
        "_subgraphId": "coding_check",
        "dynamicValue": [
            {"path": "model_tier", "expression": {"expression": "small"}},
            {"path": "prompt_config_id", "expression": {"expression": ""}},
            {
                "path": "prompt_config_name",
                "expression": {"expression": "coding_check"},
            },
            {"path": "prompt_config_version", "expression": {"expression": "1"}},
        ],
    },
    {
        "id": "ad-condition-coding-route",
        "resourceType": "ActivityDefinition",
        "name": "Route After Coding Check",
        "status": "active",
        "description": "Condition node that routes coding issues to HITL queue",
        "_subgraphId": "condition",
        "dynamicValue": [
            {
                "path": "rules",
                "expression": {
                    "expression": [
                        {
                            "field": "has_coding_issues",
                            "operator": "==",
                            "value": True,
                            "outputPort": "issues",
                        }
                    ]
                },
            },
            {"path": "defaultPort", "expression": {"expression": "clean"}},
        ],
    },
    {
        "id": "ad-hitl-coding-queue",
        "resourceType": "ActivityDefinition",
        "name": "Queue Coding HITL Review",
        "status": "active",
        "description": "Writes coding-change training candidates with HITL guidance",
        "_subgraphId": "hitl_coding_queue",
    },
    {
        "id": "ad-persist-patient",
        "resourceType": "ActivityDefinition",
        "name": "Persist to Patient Graph",
        "status": "active",
        "description": "Write coded entities and documents to patient graph",
        "_subgraphId": "persist",
        "dynamicValue": [
            {"path": "output_target", "expression": {"expression": "patient_graph"}},
        ],
    },
    {
        "id": "ad-persist-training",
        "resourceType": "ActivityDefinition",
        "name": "Persist to Gold Training",
        "status": "active",
        "description": "Write verified entities to gold training dataset",
        "_subgraphId": "persist",
        "dynamicValue": [
            {"path": "output_target", "expression": {"expression": "gold_training"}},
        ],
    },
    {
        "id": "ad-persist-both",
        "resourceType": "ActivityDefinition",
        "name": "Persist to Patient and Gold Training",
        "status": "active",
        "description": "Write coded entities to patient graph and de-identified training candidate store",
        "_subgraphId": "persist",
        "dynamicValue": [
            {"path": "output_target", "expression": {"expression": "both"}},
        ],
    },
    {
        "id": "ad-surface-form-validation",
        "resourceType": "ActivityDefinition",
        "name": "Surface Form Validation",
        "status": "active",
        "description": "Validate SNOMED mapping against extracted surface forms and create review tasks for low-confidence mismatches",
        "_subgraphId": "surface_form_validation",
        "dynamicValue": [
            {
                "path": "surface_form_validation_threshold",
                "expression": {"expression": "0.9"},
            },
        ],
    },
    {
        "id": "ad-anchor-detect",
        "resourceType": "ActivityDefinition",
        "name": "Anchor Detection",
        "status": "active",
        "description": "Detect cancer pathway anchor terms in coded entities",
        "_subgraphId": "anchor_detect",
    },
    {
        "id": "ad-episode-build",
        "resourceType": "ActivityDefinition",
        "name": "Episode Builder",
        "status": "active",
        "description": "Construct episodes of care from temporal entity sequences",
        "_subgraphId": "episode_build",
    },
    {
        "id": "ad-episode-engine",
        "resourceType": "ActivityDefinition",
        "name": "Episode Engine (AI)",
        "status": "active",
        "description": (
            "Read the patient timeline with a Haiku LangGraph agent chain "
            "(segmenter -> classifier -> milestone extractor -> reconciler) "
            "and write EpisodeOfCare nodes with milestone evidence."
        ),
        "_subgraphId": "episode_engine",
    },
    {
        "id": "ad-safety-net",
        "resourceType": "ActivityDefinition",
        "name": "Safety Netting",
        "status": "active",
        "description": "Detect missing follow-ups and safety netting signals",
        "_subgraphId": "safety_net",
    },
    {
        "id": "ad-quality-check",
        "resourceType": "ActivityDefinition",
        "name": "Quality Check",
        "status": "active",
        "description": "Detect quality issues and coding inconsistencies",
        "_subgraphId": "quality_check",
    },
    {
        "id": "ad-sbar",
        "resourceType": "ActivityDefinition",
        "name": "SBAR Generation",
        "status": "active",
        "description": "Generate SBAR clinical summary for referral documents",
        "_subgraphId": "sbar",
    },
    {
        "id": "ad-compliance",
        "resourceType": "ActivityDefinition",
        "name": "Compliance Evaluation",
        "status": "active",
        "description": "Evaluate referral compliance against pathway checklist",
        "_subgraphId": "compliance",
    },
    {
        "id": "ad-next-best-action",
        "resourceType": "ActivityDefinition",
        "name": "Next Best Action",
        "status": "active",
        "description": "Recommend clinical next-best-action based on patient state",
        "_subgraphId": "next_best_action",
    },
    {
        "id": "ad-human-review-gate",
        "resourceType": "ActivityDefinition",
        "name": "Human Review Gate",
        "status": "active",
        "description": "Pause workflow output for human clinical review",
        "_subgraphId": "human_review_gate",
    },
]


PLAN_DEFINITIONS = [
    {
        "id": "pd-gp-encounter-coding",
        "resourceType": "PlanDefinition",
        "name": "GP Encounter Coding",
        "status": "active",
        "description": "Primary care encounter NER extraction, terminology resolution, and persistence. Triggers on new encounter data. Includes optional analytics (anchor detection, episode building, safety netting, quality checks).",
        "action": [
            {
                "id": "act-load-encounter",
                "title": "Load Encounter Text",
                "_sequence": 0,
                "_subgraphId": "encounter_loader",
                "trigger": [{"type": "data-changed", "name": "encounter-created"}],
                "definitionCanonical": "ActivityDefinition/ad-encounter-loader",
            },
            {
                "id": "act-extract",
                "title": "Extract Entities",
                "_sequence": 1,
                "_subgraphId": "extraction",
                "definitionCanonical": "ActivityDefinition/ad-extraction-ner",
                "relatedAction": [
                    {"actionId": "act-load-encounter", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-post-process",
                "title": "Post-Process",
                "_sequence": 2,
                "_subgraphId": "post_processing",
                "definitionCanonical": "ActivityDefinition/ad-post-processing",
                "relatedAction": [
                    {"actionId": "act-extract", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-relation-link",
                "title": "Link Entity Relations",
                "_sequence": 3,
                "_subgraphId": "relation_linking",
                "definitionCanonical": "ActivityDefinition/ad-relation-linking",
                "relatedAction": [
                    {"actionId": "act-post-process", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-extraction-check",
                "title": "Extraction Quality Check",
                "_sequence": 4,
                "_subgraphId": "extraction_check",
                "definitionCanonical": "ActivityDefinition/ad-extraction-check",
                "relatedAction": [
                    {"actionId": "act-relation-link", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-extraction-route",
                "title": "Route Extraction Outcome",
                "_sequence": 5,
                "_subgraphId": "condition",
                "_nodeType": "condition",
                "definitionCanonical": "ActivityDefinition/ad-condition-extraction-route",
                "relatedAction": [
                    {"actionId": "act-extraction-check", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-hitl-ner-queue",
                "title": "Queue NER HITL",
                "_sequence": 6,
                "_subgraphId": "hitl_ner_queue",
                "definitionCanonical": "ActivityDefinition/ad-hitl-ner-queue",
                "relatedAction": [
                    {"actionId": "act-extraction-route", "relationship": "after-end"}
                ],
                "relatedActionEdges": [
                    {"actionId": "act-extraction-route", "sourceHandle": "changed"}
                ],
            },
            {
                "id": "act-terminology",
                "title": "Resolve Terminology",
                "_sequence": 7,
                "_subgraphId": "terminology",
                "definitionCanonical": "ActivityDefinition/ad-terminology",
                "relatedAction": [
                    {"actionId": "act-extraction-route", "relationship": "after-end"}
                ],
                "relatedActionEdges": [
                    {
                        "actionId": "act-extraction-route",
                        "sourceHandle": "pass_through",
                    }
                ],
            },
            {
                "id": "act-coding-route",
                "title": "Route Coding Outcome",
                "_sequence": 8,
                "_subgraphId": "condition",
                "_nodeType": "condition",
                "definitionCanonical": "ActivityDefinition/ad-condition-coding-route",
                "relatedAction": [
                    {"actionId": "act-terminology", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-hitl-coding-queue",
                "title": "Queue Coding HITL",
                "_sequence": 9,
                "_subgraphId": "hitl_coding_queue",
                "definitionCanonical": "ActivityDefinition/ad-hitl-coding-queue",
                "relatedAction": [
                    {"actionId": "act-coding-route", "relationship": "after-end"}
                ],
                "relatedActionEdges": [
                    {"actionId": "act-coding-route", "sourceHandle": "issues"}
                ],
            },
            {
                "id": "act-tier-classify",
                "title": "Classify Tiers",
                "_sequence": 10,
                "_subgraphId": "tier_classify",
                "definitionCanonical": "ActivityDefinition/ad-tier-classify",
                "relatedAction": [
                    {"actionId": "act-coding-route", "relationship": "after-end"}
                ],
                "relatedActionEdges": [
                    {"actionId": "act-coding-route", "sourceHandle": "clean"}
                ],
            },
            {
                "id": "act-persist",
                "title": "Persist to Patient Graph and Gold Training",
                "_sequence": 11,
                "_subgraphId": "persist",
                "definitionCanonical": "ActivityDefinition/ad-persist-both",
                "relatedAction": [
                    {"actionId": "act-tier-classify", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-anchor",
                "title": "Detect Anchors",
                "_sequence": 12,
                "_subgraphId": "anchor_detect",
                "definitionCanonical": "ActivityDefinition/ad-anchor-detect",
                "relatedAction": [
                    {"actionId": "act-persist", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-episode",
                "title": "Build Episodes",
                "_sequence": 13,
                "_subgraphId": "episode_build",
                "definitionCanonical": "ActivityDefinition/ad-episode-build",
                "relatedAction": [
                    {"actionId": "act-anchor", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-safety-net",
                "title": "Safety Netting",
                "_sequence": 14,
                "_subgraphId": "safety_net",
                "definitionCanonical": "ActivityDefinition/ad-safety-net",
                "relatedAction": [
                    {"actionId": "act-episode", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-quality",
                "title": "Quality Check",
                "_sequence": 15,
                "_subgraphId": "quality_check",
                "definitionCanonical": "ActivityDefinition/ad-quality-check",
                "relatedAction": [
                    {"actionId": "act-safety-net", "relationship": "after-end"}
                ],
            },
        ],
    },
    {
        "id": "pd-referral-assessment",
        "resourceType": "PlanDefinition",
        "name": "Referral Assessment",
        "status": "active",
        "description": "Referral document processing: extract entities, resolve terminology, check compliance against guidance graph, generate SBAR summary with next-best-action recommendation.",
        "action": [
            {
                "id": "act-ref-extract",
                "title": "Extract Entities",
                "_sequence": 0,
                "_subgraphId": "extraction",
                "trigger": [{"type": "data-changed", "name": "referral-received"}],
                "definitionCanonical": "ActivityDefinition/ad-extraction-llm",
            },
            {
                "id": "act-ref-post-process",
                "title": "Post-Process",
                "_sequence": 1,
                "_subgraphId": "post_processing",
                "definitionCanonical": "ActivityDefinition/ad-post-processing",
                "relatedAction": [
                    {"actionId": "act-ref-extract", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-ref-terminology",
                "title": "Resolve Terminology",
                "_sequence": 2,
                "_subgraphId": "terminology",
                "definitionCanonical": "ActivityDefinition/ad-terminology",
                "relatedAction": [
                    {"actionId": "act-ref-post-process", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-ref-compliance",
                "title": "Compliance Check",
                "_sequence": 3,
                "_subgraphId": "compliance",
                "definitionCanonical": "ActivityDefinition/ad-compliance",
                "relatedAction": [
                    {"actionId": "act-ref-terminology", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-ref-sbar",
                "title": "Generate SBAR",
                "_sequence": 4,
                "_subgraphId": "sbar",
                "definitionCanonical": "ActivityDefinition/ad-sbar",
                "relatedAction": [
                    {"actionId": "act-ref-compliance", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-ref-nba",
                "title": "Next Best Action",
                "_sequence": 5,
                "_subgraphId": "next_best_action",
                "definitionCanonical": "ActivityDefinition/ad-next-best-action",
                "relatedAction": [
                    {"actionId": "act-ref-sbar", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-ref-persist",
                "title": "Persist Results",
                "_sequence": 6,
                "_subgraphId": "persist",
                "definitionCanonical": "ActivityDefinition/ad-persist-patient",
                "relatedAction": [
                    {"actionId": "act-ref-nba", "relationship": "after-end"}
                ],
            },
        ],
    },
    {
        "id": "pd-gold-training-audit",
        "resourceType": "PlanDefinition",
        "name": "Gold Training Data",
        "status": "active",
        "description": "Gold-standard NER training pipeline: extract with LLM, verify with big model, persist verified results as gold training labels.",
        "action": [
            {
                "id": "act-gold-extract",
                "title": "Extract Entities (LLM)",
                "_sequence": 0,
                "_subgraphId": "extraction",
                "trigger": [{"type": "data-changed", "name": "training-run-requested"}],
                "definitionCanonical": "ActivityDefinition/ad-extraction-llm",
            },
            {
                "id": "act-gold-post-process",
                "title": "Post-Process",
                "_sequence": 1,
                "_subgraphId": "post_processing",
                "definitionCanonical": "ActivityDefinition/ad-post-processing",
                "relatedAction": [
                    {"actionId": "act-gold-extract", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-gold-relation-link",
                "title": "Link Entity Relations",
                "_sequence": 2,
                "_subgraphId": "relation_linking",
                "definitionCanonical": "ActivityDefinition/ad-relation-linking",
                "relatedAction": [
                    {"actionId": "act-gold-post-process", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-gold-extraction-check",
                "title": "Extraction Quality Check",
                "_sequence": 3,
                "_subgraphId": "extraction_check",
                "definitionCanonical": "ActivityDefinition/ad-extraction-check",
                "relatedAction": [
                    {"actionId": "act-gold-relation-link", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-gold-verify",
                "title": "Big-Model Verification",
                "_sequence": 4,
                "_subgraphId": "verification",
                "definitionCanonical": "ActivityDefinition/ad-verification",
                "relatedAction": [
                    {
                        "actionId": "act-gold-extraction-check",
                        "relationship": "after-end",
                    }
                ],
            },
            {
                "id": "act-gold-terminology",
                "title": "Resolve Terminology",
                "_sequence": 5,
                "_subgraphId": "terminology",
                "definitionCanonical": "ActivityDefinition/ad-terminology",
                "relatedAction": [
                    {"actionId": "act-gold-verify", "relationship": "after-end"}
                ],
            },
            {
                "id": "act-gold-persist",
                "title": "Persist Gold Labels",
                "_sequence": 7,
                "_subgraphId": "persist",
                "definitionCanonical": "ActivityDefinition/ad-persist-training",
                "relatedAction": [
                    {
                        "actionId": "act-gold-surface-form-validation",
                        "relationship": "after-end",
                    }
                ],
            },
            {
                "id": "act-gold-surface-form-validation",
                "title": "Surface Form Validation",
                "_sequence": 6,
                "_subgraphId": "surface_form_validation",
                "definitionCanonical": "ActivityDefinition/ad-surface-form-validation",
                "relatedAction": [
                    {"actionId": "act-gold-terminology", "relationship": "after-end"}
                ],
            },
        ],
    },
] + all_validation_plan_definitions()


def _to_ui_format(pd_def: dict) -> dict:
    """Convert a FHIR PlanDefinition to the UI-friendly format expected by the pathway builder.

    The UI expects:
    - actions: [{id, subgraphId, label, position: {x, y}, config: {...}}]
    - edges: [{source, target}]
    - trigger: {event, description}

    This keeps the FHIR `action` array intact for the WorkflowEngine,
    and adds the UI properties alongside it.
    """
    fhir_actions = pd_def.get("action", [])
    ui_actions = []
    ui_edges = []

    for i, act in enumerate(fhir_actions):
        trigger = (act.get("trigger") or [{}])[0]
        trigger_event = trigger.get("name", "")
        definition_ref = act.get("definitionCanonical", "")
        activity_id = definition_ref.split("/")[-1] if definition_ref else ""

        ad_lookup = {a["id"]: a for a in ACTIVITY_DEFINITIONS}
        ad = ad_lookup.get(activity_id, {})
        dv = ad.get("dynamicValue", [])
        config: dict = {}
        for v in dv:
            path = v.get("path", "")
            expr = v.get("expression", {}).get("expression", "")
            if path == "extraction_method":
                config["extractionMethod"] = expr
            elif path == "prompt_config_id":
                config["promptConfigId"] = expr
            elif path == "prompt_config_name":
                config["promptConfigName"] = expr
            elif path == "prompt_config_version":
                try:
                    config["promptConfigVersion"] = int(expr)
                except (TypeError, ValueError):
                    config["promptConfigVersion"] = 1
            elif path == "output_target":
                config["outputTarget"] = expr
            elif path == "model_tier":
                config["modelTier"] = expr
            elif path == "max_retries":
                config["maxRetries"] = int(expr) if str(expr).isdigit() else 2
            elif path == "confidence_threshold":
                try:
                    config["confidenceThreshold"] = float(expr)
                except (TypeError, ValueError):
                    pass
            elif path == "rules":
                raw_rules = expr if isinstance(expr, list) else []
                params = config.setdefault("params", {})
                params["rules"] = [
                    {
                        "id": f"rule_{i}",
                        "field": r.get("field", ""),
                        "operator": r.get("operator", "=="),
                        "value": (
                            str(r.get("value", "")).lower()
                            if isinstance(r.get("value"), bool)
                            else str(r.get("value", ""))
                        ),
                        "outputPort": r.get("outputPort", ""),
                    }
                    for i, r in enumerate(raw_rules)
                ]
            elif path == "defaultPort":
                config.setdefault("params", {})["defaultPort"] = expr

        ui_actions.append(
            {
                "id": act["id"],
                "subgraphId": act.get("_subgraphId", ""),
                "label": act.get("title", act.get("_subgraphId", "")),
                "nodeType": act.get("_nodeType", "action"),
                "position": {"x": 250, "y": 80 + i * 160},
                "config": config,
            }
        )

        # Build a set of sources that already have a typed edge (sourceHandle present)
        # so the plain relatedAction fallback edge is not duplicated.
        typed_edge_sources = {
            rel.get("actionId", "")
            for rel in act.get("relatedActionEdges", [])
            if rel.get("actionId")
        }
        for rel in act.get("relatedAction", []):
            source_id = rel.get("actionId", "")
            if source_id and source_id not in typed_edge_sources:
                ui_edges.append({"source": source_id, "target": act["id"]})
        for rel in act.get("relatedActionEdges", []):
            source_id = rel.get("actionId", "")
            if source_id:
                ui_edges.append(
                    {
                        "source": source_id,
                        "target": act["id"],
                        "sourceHandle": rel.get("sourceHandle"),
                        "targetHandle": rel.get("targetHandle"),
                    }
                )

    trigger_action_id = ""
    for act in fhir_actions:
        if act.get("trigger"):
            trigger_action_id = act.get("id", "")
            break
    if trigger_action_id:
        ui_actions.insert(
            0,
            {
                "id": "__source__",
                "subgraphId": "source",
                "label": "Start",
                "nodeType": "source",
                "position": {"x": 60, "y": 80},
                "config": {},
            },
        )
        ui_edges.insert(0, {"source": "__source__", "target": trigger_action_id})

    result = dict(pd_def)
    result["actions"] = ui_actions
    result["edges"] = ui_edges

    first_trigger = {}
    for act in fhir_actions:
        triggers = act.get("trigger", [])
        if triggers:
            t = triggers[0]
            first_trigger = {"event": t.get("name", ""), "type": t.get("type", "")}
            break
    if first_trigger:
        result["trigger"] = first_trigger

    return result


UPSERT_ACTIVITY = """
MERGE (ad:ActivityDefinition {id: $id})
SET ad.rawJson = $raw,
    ad.name = $name,
    ad.status = $status,
    ad.subgraphId = $subgraph_id,
    ad.dynamicValues = $dynamic_values,
    ad.isGlobal = true
"""

UPSERT_PLAN = """
MERGE (pd:PlanDefinition {id: $id})
SET pd.rawJson = $raw,
    pd.name = $name,
    pd.status = $status,
    pd.isGlobal = true,
    pd.source = 'seed'
"""

CLEAR_ACTIONS = """
MATCH (pd:PlanDefinition {id: $id})-[r:HAS_ACTION]->(a:Action)
DETACH DELETE a
"""

CREATE_ACTION = """
MATCH (pd:PlanDefinition {id: $plan_id})
CREATE (pd)-[:HAS_ACTION]->(a:Action {
  id: $action_id,
  canvas_id: $action_id,
  nodeType: $node_type,
  trigger_type: $trigger_type,
  trigger_name: $trigger_name,
  condition: $condition,
  sequence: $sequence,
  subgraphId: $subgraph_id,
  relatedActions: $related_actions,
  relatedActionEdges: $related_action_edges
})
"""

LINK_ACTIVITY = """
MATCH (a:Action {id: $action_id})
MATCH (ad:ActivityDefinition {id: $activity_id})
MERGE (a)-[:USES_DEFINITION]->(ad)
"""


COUNT_PLANS = "MATCH (pd:PlanDefinition) RETURN count(pd) AS cnt"
COUNT_PLAN_BY_ID = "MATCH (pd:PlanDefinition {id: $id}) RETURN count(pd) AS cnt"
GET_PROMPT_CONFIG_EXTRACTION = """
MATCH (p:PromptConfig {name: 'extraction', version: 1})
RETURN p.id AS id
LIMIT 1
"""


def _wire_extraction_prompt_config(client) -> None:
    rows = client.run(GET_PROMPT_CONFIG_EXTRACTION)
    if not rows:
        logger.info(
            "[Seed] PromptConfig extraction v1 not found; keeping prompt_config_id empty."
        )
        return
    prompt_config_id = str(rows[0].get("id") or "").strip()
    if not prompt_config_id:
        return
    for ad in ACTIVITY_DEFINITIONS:
        if ad.get("id") != "ad-extraction-llm":
            continue
        dynamic_values = ad.setdefault("dynamicValue", [])
        found = False
        for dv in dynamic_values:
            if dv.get("path") == "prompt_config_id":
                dv.setdefault("expression", {})["expression"] = prompt_config_id
                found = True
                break
        if not found:
            dynamic_values.append(
                {
                    "path": "prompt_config_id",
                    "expression": {"expression": prompt_config_id},
                }
            )
    logger.info("[Seed] Wired ad-extraction-llm prompt_config_id=%s", prompt_config_id)


def seed_with_client(client, *, force: bool = False) -> None:
    """Seed PlanDefinitions using an existing KnowledgeGraphClient (for startup hooks).

    Only seeds when no PlanDefinitions exist in Neo4j, to avoid
    overwriting user-modified pipelines.
    """
    try:
        client.run(
            "CREATE CONSTRAINT plan_def_id IF NOT EXISTS FOR (pd:PlanDefinition) REQUIRE pd.id IS UNIQUE"
        )
        client.run(
            "CREATE CONSTRAINT activity_def_id IF NOT EXISTS FOR (ad:ActivityDefinition) REQUIRE ad.id IS UNIQUE"
        )
        client.run(
            "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (a:Action) REQUIRE a.id IS UNIQUE"
        )

        _wire_extraction_prompt_config(client)

        for ad in ACTIVITY_DEFINITIONS:
            dv = ad.get("dynamicValue", [])
            dv_json = (
                json.dumps(
                    {v["path"]: v.get("expression", {}).get("expression") for v in dv}
                )
                if dv
                else None
            )
            client.run(
                UPSERT_ACTIVITY,
                id=ad["id"],
                raw=json.dumps(ad),
                name=ad["name"],
                status=ad["status"],
                subgraph_id=ad.get("_subgraphId", ""),
                dynamic_values=dv_json,
            )

        for pd in PLAN_DEFINITIONS:
            existing_row = client.run(COUNT_PLAN_BY_ID, id=pd["id"])
            existing_count = int(existing_row[0]["cnt"]) if existing_row else 0
            if existing_count > 0 and not force:
                logger.info("[Seed] Skipped existing PlanDefinition id=%s", pd["id"])
                continue
            ui_pd = _to_ui_format(pd)
            ui_pd["meta"] = {
                "seeded": True,
                "seededBy": "scripts/seed_plan_definitions.py",
            }
            client.run(
                UPSERT_PLAN,
                id=pd["id"],
                raw=json.dumps(ui_pd),
                name=pd["name"],
                status=pd["status"],
            )
            client.run(CLEAR_ACTIONS, id=pd["id"])
            for action in pd.get("action", []):
                trigger = (action.get("trigger") or [{}])[0]
                definition_ref = action.get("definitionCanonical", "")
                related_ids = [
                    r.get("actionId", "") for r in (action.get("relatedAction") or [])
                ]
                related_edges = action.get("relatedActionEdges") or []
                client.run(
                    CREATE_ACTION,
                    plan_id=pd["id"],
                    action_id=action["id"],
                    node_type=action.get("_nodeType", "action"),
                    trigger_type=trigger.get("type", ""),
                    trigger_name=trigger.get("name", ""),
                    condition=None,
                    sequence=action.get("_sequence", 0),
                    subgraph_id=action.get("_subgraphId", ""),
                    related_actions=related_ids,
                    related_action_edges=json.dumps(related_edges),
                )
                if definition_ref:
                    activity_id = definition_ref.split("/")[-1]
                    client.run(
                        LINK_ACTIVITY, action_id=action["id"], activity_id=activity_id
                    )

        logger.info(
            "[Seed] %d ActivityDefinitions processed, %d PlanDefinitions processed (force=%s).",
            len(ACTIVITY_DEFINITIONS),
            len(PLAN_DEFINITIONS),
            force,
        )
    except Exception as exc:
        logger.warning("[Seed] PlanDefinition seed failed (non-fatal): %s", exc)


def main() -> None:
    from neo4j import GraphDatabase

    parser = argparse.ArgumentParser(
        description="Seed PlanDefinitions and ActivityDefinitions"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing seeded plan definitions by id",
    )
    args = parser.parse_args()

    uri = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687")
    )
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password")
    )

    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT plan_def_id IF NOT EXISTS FOR (pd:PlanDefinition) REQUIRE pd.id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT activity_def_id IF NOT EXISTS FOR (ad:ActivityDefinition) REQUIRE ad.id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (a:Action) REQUIRE a.id IS UNIQUE"
        )
    logger.info("Constraints ensured.")

    with driver.session() as session:
        prompt_row = session.run(GET_PROMPT_CONFIG_EXTRACTION).single()
    prompt_config_id = (
        str(prompt_row["id"]) if prompt_row and prompt_row.get("id") else ""
    )
    if prompt_config_id:
        for ad in ACTIVITY_DEFINITIONS:
            if ad.get("id") != "ad-extraction-llm":
                continue
            dynamic_values = ad.setdefault("dynamicValue", [])
            for dv in dynamic_values:
                if dv.get("path") == "prompt_config_id":
                    dv.setdefault("expression", {})["expression"] = prompt_config_id
                    break

    for ad in ACTIVITY_DEFINITIONS:
        dv = ad.get("dynamicValue", [])
        dv_json = (
            json.dumps(
                {v["path"]: v.get("expression", {}).get("expression") for v in dv}
            )
            if dv
            else None
        )
        with driver.session() as session:
            session.run(
                UPSERT_ACTIVITY,
                id=ad["id"],
                raw=json.dumps(ad),
                name=ad["name"],
                status=ad["status"],
                subgraph_id=ad.get("_subgraphId", ""),
                dynamic_values=dv_json,
            )
        logger.info("  ActivityDefinition: %s", ad["name"])

    for pd in PLAN_DEFINITIONS:
        with driver.session() as session:
            existing = session.run(COUNT_PLAN_BY_ID, id=pd["id"]).single()
            existing_count = int(existing["cnt"]) if existing else 0
        if existing_count > 0 and not args.force:
            logger.info("  Skipped existing PlanDefinition: %s", pd["id"])
            continue

        ui_pd = _to_ui_format(pd)
        with driver.session() as session:
            session.run(
                UPSERT_PLAN,
                id=pd["id"],
                raw=json.dumps(ui_pd),
                name=pd["name"],
                status=pd["status"],
            )
            session.run(CLEAR_ACTIONS, id=pd["id"])

        for action in pd.get("action", []):
            trigger = (action.get("trigger") or [{}])[0]
            trigger_type = trigger.get("type", "")
            trigger_name = trigger.get("name", "")
            definition_ref = action.get("definitionCanonical", "")
            related_ids = [
                r.get("actionId", "") for r in (action.get("relatedAction") or [])
            ]
            related_edges = action.get("relatedActionEdges") or []

            with driver.session() as session:
                session.run(
                    CREATE_ACTION,
                    plan_id=pd["id"],
                    action_id=action["id"],
                    node_type=action.get("_nodeType", "action"),
                    trigger_type=trigger_type,
                    trigger_name=trigger_name,
                    condition=None,
                    sequence=action.get("_sequence", 0),
                    subgraph_id=action.get("_subgraphId", ""),
                    related_actions=related_ids,
                    related_action_edges=json.dumps(related_edges),
                )
                if definition_ref:
                    activity_id = definition_ref.split("/")[-1]
                    session.run(
                        LINK_ACTIVITY, action_id=action["id"], activity_id=activity_id
                    )

        logger.info(
            "  PlanDefinition: %s (%d actions)", pd["name"], len(pd.get("action", []))
        )

    driver.close()
    logger.info(
        "Done. %d ActivityDefinitions processed, %d PlanDefinitions processed (force=%s).",
        len(ACTIVITY_DEFINITIONS),
        len(PLAN_DEFINITIONS),
        args.force,
    )


if __name__ == "__main__":
    main()
