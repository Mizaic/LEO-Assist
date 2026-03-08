"""Subgraph registry for the clinical pipeline.

Subgraphs are registered by ID and can be looked up at runtime by the
WorkflowEngine when dispatching ActivityDefinition-driven pipeline steps.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

BuilderFn = Callable[..., CompiledStateGraph]


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
            {"id": sid, **self._metadata.get(sid, {})}
            for sid in sorted(self._builders)
        ]

    def has(self, subgraph_id: str) -> bool:
        return subgraph_id in self._builders


_default_registry: SubgraphRegistry | None = None


def get_registry() -> SubgraphRegistry:
    """Return the global default subgraph registry, creating it on first call."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SubgraphRegistry()
        _register_defaults(_default_registry)
    return _default_registry


def _register_defaults(registry: SubgraphRegistry) -> None:
    """Register all built-in subgraphs."""
    from libs.pipeline_graph.subgraphs.extraction import build_extraction_subgraph
    from libs.pipeline_graph.subgraphs.post_processing import build_post_processing_subgraph
    from libs.pipeline_graph.subgraphs.terminology import build_terminology_subgraph
    from libs.pipeline_graph.subgraphs.tier_classify import build_tier_classify_subgraph
    from libs.pipeline_graph.subgraphs.verification import build_verification_subgraph
    from libs.pipeline_graph.subgraphs.persist import build_persist_subgraph
    from libs.pipeline_graph.subgraphs.anchor import build_anchor_subgraph
    from libs.pipeline_graph.subgraphs.episode import build_episode_subgraph
    from libs.pipeline_graph.subgraphs.safety_net import build_safety_net_subgraph
    from libs.pipeline_graph.subgraphs.quality_check import build_quality_check_subgraph
    from libs.pipeline_graph.subgraphs.sbar import build_sbar_subgraph
    from libs.pipeline_graph.subgraphs.compliance import build_compliance_subgraph
    from libs.pipeline_graph.subgraphs.next_best_action import build_nba_subgraph
    from libs.pipeline_graph.subgraphs.surface_form_validation import (
        build_surface_form_validation_subgraph,
    )
    from libs.pipeline_graph.subgraphs.rest_connector import build_rest_connector_subgraph
    from libs.pipeline_graph.subgraphs.queue_publish import build_queue_publish_subgraph
    from libs.pipeline_graph.subgraphs.guidance_rule_extraction import (
        build_guidance_rule_extraction_subgraph,
    )

    registry.register("extraction", build_extraction_subgraph, description="NER/LLM entity extraction")
    registry.register("post_processing", build_post_processing_subgraph, description="9-layer post-processing pipeline")
    registry.register("terminology", build_terminology_subgraph, description="SNOMED terminology resolution")
    registry.register("tier_classify", build_tier_classify_subgraph, description="Three-tier confidence classification")
    registry.register("verification", build_verification_subgraph, description="Big-model verification with retry")
    registry.register("persist", build_persist_subgraph, description="Write to patient graph or gold training")
    registry.register("anchor_detect", build_anchor_subgraph, description="Cancer pathway anchor detection")
    registry.register("episode_build", build_episode_subgraph, description="Episode of care construction")
    registry.register("safety_net", build_safety_net_subgraph, description="Safety netting signal detection")
    registry.register("quality_check", build_quality_check_subgraph, description="Quality issue detection")
    registry.register("sbar", build_sbar_subgraph, description="SBAR report generation")
    registry.register("compliance", build_compliance_subgraph, description="Referral compliance evaluation")
    registry.register("next_best_action", build_nba_subgraph, description="Clinical next-best-action recommendation")
    registry.register(
        "surface_form_validation",
        build_surface_form_validation_subgraph,
        description="Validate/correct surface form to SNOMED mappings",
    )
    registry.register(
        "rest_connector",
        build_rest_connector_subgraph,
        description="External REST API connector step",
    )
    registry.register(
        "queue_publish",
        build_queue_publish_subgraph,
        description="Queue publish connector step",
    )
    registry.register(
        "guidance_rule_extraction",
        build_guidance_rule_extraction_subgraph,
        description=(
            "NICE → AppropriatenessRule: extracts patient criteria (present/absent "
            "SNOMED findings) and the recommended action (SNOMED procedure) from a "
            "single NICE recommendation using the dual-model consensus pipeline."
        ),
        input_schema=json.dumps({
            "recommendation": "Recommendation dict (id, verbatim, title, urgency, strength, section_title, chapter_title)",
            "guideline_id": "NICE guideline code e.g. NG12",
            "prompt_config": "Optional PromptConfig dict (systemPrompt key) — loaded from /admin/prompts if omitted",
        }),
        output_schema=json.dumps({
            "coded_criteria": {
                "present": "list of {term, snomed_concept_id, preferred_term, semantic_tag}",
                "absent":  "list of {term, snomed_concept_id, preferred_term, semantic_tag}",
                "action":  "{term, snomed_concept_id, preferred_term, semantic_tag} or null",
            },
            "errors": "list of error strings",
        }),
    )
