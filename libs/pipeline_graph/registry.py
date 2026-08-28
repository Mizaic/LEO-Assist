"""Subgraph registry for the clinical pipeline.

Atlas trace:
  DO: DO-14B332AB
  Also implements: DO-8620A68B, DO-93E086B0, DO-A26CD350
  DI: DI-30D95132, DI-5A802C83, DI-705C806B, DI-F2C18D2E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-14B332AB")

Subgraphs are registered by ID and can be looked up at runtime by the
WorkflowEngine when dispatching ActivityDefinition-driven pipeline steps.
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

BuilderFn = Callable[..., CompiledStateGraph]


class SubgraphRegistrationError(RuntimeError):
    """A built-in pipeline stage could not be loaded, so startup must stop.

    A stage that is quietly missing means the worker runs a shorter
    pipeline than the plan asks for, and a run can skip a clinical stage
    while still looking normal. See rule 5 of
    .cursor/rules/fail-closed-boundary.mdc.
    """


@dataclass(frozen=True)
class _SubgraphSpec:
    """Where to find one built-in subgraph builder, and how to describe it."""

    subgraph_id: str
    module: str
    builder: str
    description: str = ""
    input_schema: str = ""
    output_schema: str = ""


class SubgraphRegistry:
    """Registry of available LangGraph subgraphs.

    Each subgraph is registered with a unique ID and a builder function
    that produces a compiled StateGraph when called.
    """

    def __init__(self) -> None:
        self._builders: dict[str, BuilderFn] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        subgraph_id: str,
        builder: BuilderFn,
        *,
        description: str = "",
        input_schema: str = "",
        output_schema: str = "",
    ) -> None:
        """Register a subgraph builder function."""
        if subgraph_id in self._builders:
            logger.warning("Overwriting subgraph registration: %s", subgraph_id)
        self._builders[subgraph_id] = builder
        self._metadata[subgraph_id] = {
            "description": description,
            "input_schema": input_schema,
            "output_schema": output_schema,
        }

    def build(self, subgraph_id: str, **kwargs: Any) -> CompiledStateGraph:
        """Build and return a compiled subgraph by ID.

        Raises KeyError if the subgraph_id is not registered.
        """
        if subgraph_id not in self._builders:
            raise KeyError(
                f"Subgraph '{subgraph_id}' not registered. "
                f"Available: {list(self._builders.keys())}"
            )
        return self._builders[subgraph_id](**kwargs)

    def list_subgraphs(self) -> list[dict[str, Any]]:
        """Return metadata for all registered subgraphs."""
        return [
            {"id": sid, **self._metadata.get(sid, {})} for sid in sorted(self._builders)
        ]

    def has(self, subgraph_id: str) -> bool:
        return subgraph_id in self._builders


_default_registry: SubgraphRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> SubgraphRegistry:
    """Return the global default subgraph registry, creating it on first call.

    Thread-safe: uses double-checked locking. The registry is assigned to the
    module global ONLY after _register_defaults() completes, so no thread can
    observe a partially-initialised registry.
    """
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                reg = SubgraphRegistry()
                _register_defaults(reg)
                _default_registry = reg  # assign AFTER registration is complete
    return _default_registry


_EPISODE_ENGINE_INPUT = json.dumps(
    {
        "patient_id": "Patient ID",
        "domain_id": "Domain ID",
        "dry_run": "bool",
    }
)
_EPISODE_ENGINE_OUTPUT = json.dumps(
    {
        "written_episodes": "Final Episode dicts",
        "trace_id": "Engine trace id",
    }
)
_GUIDANCE_RULE_INPUT = json.dumps(
    {
        "recommendation": (
            "Recommendation dict (id, verbatim, title, urgency, strength, "
            "section_title, chapter_title, list_structure / list_structure_json)"
        ),
        "guideline_id": "NICE guideline code e.g. NG12",
        "triage_bucket": (
            "Optional triage bucket (full_rule / trigger_plus_narrative / no_rule)"
        ),
        "prompt_config": (
            "Optional PromptConfig dict (systemPrompt key) -- loaded from "
            "/admin/prompts if omitted"
        ),
    }
)
_GUIDANCE_RULE_OUTPUT = json.dumps(
    {
        "coded_criteria": {
            "schema_version": 2,
            "logic_tree": (
                "schema_version 2 logic tree (AND/OR/AT_LEAST/NOT + leaves)"
            ),
            "actions": "list of action payloads (procedure or narrative)",
            "situation_windows": "optional per-situation text windows",
        },
        "errors": "list of error strings",
    }
)

_SUBGRAPHS_PACKAGE = "libs.pipeline_graph.subgraphs"

# Every entry here is mandatory. There is no optional built-in subgraph:
# each ID is also pinned in the frontend catalogue, the probe strategies,
# and the plan seed script (see .cursor/rules/pipeline-canvas-consistency).
_DEFAULT_SUBGRAPHS: tuple[_SubgraphSpec, ...] = (
    _SubgraphSpec(
        "encounter_loader",
        f"{_SUBGRAPHS_PACKAGE}.encounter_loader",
        "build_encounter_loader_subgraph",
        description="Load encounter text from Neo4j by encounter_id",
    ),
    _SubgraphSpec(
        "extraction",
        f"{_SUBGRAPHS_PACKAGE}.extraction",
        "build_extraction_subgraph",
        description="NER/LLM entity extraction",
    ),
    _SubgraphSpec(
        "post_processing",
        f"{_SUBGRAPHS_PACKAGE}.post_processing",
        "build_post_processing_subgraph",
        description="9-layer post-processing pipeline",
    ),
    _SubgraphSpec(
        "relation_linking",
        f"{_SUBGRAPHS_PACKAGE}.relation_linking",
        "build_relation_linking_subgraph",
        description="Link related extracted entities with typed relations",
    ),
    _SubgraphSpec(
        "snomed_enrichment",
        f"{_SUBGRAPHS_PACKAGE}.snomed_enrichment",
        "build_snomed_enrichment_subgraph",
        description="SNOMED-grounded relation candidates and inferred sites",
    ),
    _SubgraphSpec(
        "terminology",
        f"{_SUBGRAPHS_PACKAGE}.terminology",
        "build_terminology_subgraph",
        description="SNOMED terminology resolution",
    ),
    _SubgraphSpec(
        "coding_verifier",
        f"{_SUBGRAPHS_PACKAGE}.coding_verifier",
        "build_coding_verifier_subgraph",
        description="LLM semantic gate: accept/reject/retry proposed SNOMED codes",
    ),
    _SubgraphSpec(
        "referral_reason",
        f"{_SUBGRAPHS_PACKAGE}.referral_reason",
        "build_referral_reason_subgraph",
        description="Extracts clinical reason for referral from NHS eRS chunks",
    ),
    _SubgraphSpec(
        "sbar",
        f"{_SUBGRAPHS_PACKAGE}.sbar",
        "build_sbar_subgraph",
        description=(
            "SBAR clinical assessment: Situation/Background/Assessment/"
            "Recommendation"
        ),
    ),
    _SubgraphSpec(
        "tier_classify",
        f"{_SUBGRAPHS_PACKAGE}.tier_classify",
        "build_tier_classify_subgraph",
        description="Three-tier confidence classification",
    ),
    _SubgraphSpec(
        "verification",
        f"{_SUBGRAPHS_PACKAGE}.verification",
        "build_verification_subgraph",
        description="Big-model verification with retry",
    ),
    _SubgraphSpec(
        "extraction_check",
        f"{_SUBGRAPHS_PACKAGE}.llm_check",
        "build_extraction_check_subgraph",
        description="Single-turn extraction quality check",
    ),
    _SubgraphSpec(
        "coding_check",
        f"{_SUBGRAPHS_PACKAGE}.llm_check",
        "build_coding_check_subgraph",
        description="Single-turn coding quality check",
    ),
    _SubgraphSpec(
        "persist",
        f"{_SUBGRAPHS_PACKAGE}.persist",
        "build_persist_subgraph",
        description="Write to patient graph or gold training",
    ),
    _SubgraphSpec(
        "anchor_detect",
        f"{_SUBGRAPHS_PACKAGE}.anchor",
        "build_anchor_subgraph",
        description="Cancer pathway anchor detection",
    ),
    _SubgraphSpec(
        "episode_build",
        f"{_SUBGRAPHS_PACKAGE}.episode",
        "build_episode_subgraph",
        description="Episode of care construction (legacy rule-based)",
    ),
    _SubgraphSpec(
        "episode_engine",
        f"{_SUBGRAPHS_PACKAGE}.episode_engine",
        "build_episode_engine_pipeline_subgraph",
        description=(
            "AI-driven episode + milestone detection (Haiku LangGraph "
            "chain): segmenter -> classifier -> milestone_extractor -> "
            "reconciler -> writer."
        ),
        input_schema=_EPISODE_ENGINE_INPUT,
        output_schema=_EPISODE_ENGINE_OUTPUT,
    ),
    _SubgraphSpec(
        "staging_enrichment",
        f"{_SUBGRAPHS_PACKAGE}.staging_enrichment",
        "build_staging_enrichment_subgraph",
        description="Post-episode cancer stage enrichment",
    ),
    _SubgraphSpec(
        "safety_net",
        f"{_SUBGRAPHS_PACKAGE}.safety_net",
        "build_safety_net_subgraph",
        description="Safety netting signal detection",
    ),
    _SubgraphSpec(
        "quality_check",
        f"{_SUBGRAPHS_PACKAGE}.quality_check",
        "build_quality_check_subgraph",
        description="Quality issue detection",
    ),
    _SubgraphSpec(
        "compliance",
        f"{_SUBGRAPHS_PACKAGE}.compliance",
        "build_compliance_subgraph",
        description="Referral compliance evaluation",
    ),
    _SubgraphSpec(
        "next_best_action",
        f"{_SUBGRAPHS_PACKAGE}.next_best_action",
        "build_nba_subgraph",
        description="Clinical next-best-action recommendation",
    ),
    _SubgraphSpec(
        "surface_form_validation",
        f"{_SUBGRAPHS_PACKAGE}.surface_form_validation",
        "build_surface_form_validation_subgraph",
        description="Validate/correct surface form to SNOMED mappings",
    ),
    _SubgraphSpec(
        "rest_connector",
        f"{_SUBGRAPHS_PACKAGE}.rest_connector",
        "build_rest_connector_subgraph",
        description="External REST API connector step",
    ),
    _SubgraphSpec(
        "queue_publish",
        f"{_SUBGRAPHS_PACKAGE}.queue_publish",
        "build_queue_publish_subgraph",
        description="Queue publish connector step",
    ),
    _SubgraphSpec(
        "human_review_gate",
        f"{_SUBGRAPHS_PACKAGE}.human_review_gate",
        "build_human_review_gate_subgraph",
        description="Workflow pause gate for human clinical review",
    ),
    _SubgraphSpec(
        "hitl_ner_queue",
        f"{_SUBGRAPHS_PACKAGE}.hitl_ner_queue",
        "build_hitl_ner_queue_subgraph",
        description="Queue extraction quality changes for human review",
    ),
    _SubgraphSpec(
        "hitl_coding_queue",
        f"{_SUBGRAPHS_PACKAGE}.hitl_coding_queue",
        "build_hitl_coding_queue_subgraph",
        description="Queue coding quality changes for human review",
    ),
    _SubgraphSpec(
        "encounter_coding_agent",
        f"{_SUBGRAPHS_PACKAGE}.encounter_coding_agent",
        "build_encounter_coding_agent_subgraph",
        description=(
            "Unified encounter coding/audit agent: SNOMED tool-calling "
            "LangGraph graph for both initial coding (code mode) and audit "
            "verification (audit mode). Tier selects the Bedrock model."
        ),
    ),
    _SubgraphSpec(
        "guidance_rule_extraction",
        f"{_SUBGRAPHS_PACKAGE}.guidance_rule_extraction",
        "build_guidance_rule_extraction_subgraph",
        description=(
            "NICE -> AppropriatenessRule: builds a SituationDraft "
            "(prerequisites / situations / conditions / actions) from list "
            "structure or prose split, compiles to schema_version 2 "
            "logic_tree, and resolves SNOMED concepts for HITL review."
        ),
        input_schema=_GUIDANCE_RULE_INPUT,
        output_schema=_GUIDANCE_RULE_OUTPUT,
    ),
)


def _load_builder(spec: _SubgraphSpec) -> BuilderFn:
    """Import one subgraph builder, or raise so startup stops."""
    try:
        module = importlib.import_module(spec.module)
        return getattr(module, spec.builder)
    except Exception as exc:
        raise SubgraphRegistrationError(
            f"Cannot start: the '{spec.subgraph_id}' pipeline stage failed to "
            f"load from {spec.module}. Fix that import error, then start the "
            f"worker again. A worker must never run without this stage, "
            f"because a run would skip it and still look normal. "
            f"Cause: {exc}"
        ) from exc


def _register_defaults(registry: SubgraphRegistry) -> None:
    """Register every built-in subgraph. Any failure aborts startup.

    A subgraph that fails to import is never logged and skipped. The
    worker would then assemble a shorter pipeline than the plan asks for,
    and a run that skipped a clinical stage would look normal. See rule 5
    of .cursor/rules/fail-closed-boundary.mdc.
    """
    for spec in _DEFAULT_SUBGRAPHS:
        registry.register(
            spec.subgraph_id,
            _load_builder(spec),
            description=spec.description,
            input_schema=spec.input_schema,
            output_schema=spec.output_schema,
        )
    logger.info("Registered %d pipeline subgraphs", len(_DEFAULT_SUBGRAPHS))
