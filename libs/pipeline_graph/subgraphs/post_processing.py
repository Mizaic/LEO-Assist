"""Post-processing subgraph wrapping the canonical 9-layer pipeline.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class PostProcessingState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    enable_disorder_gate: bool
    coding_mode: str
    org_id: str
    local_concept_patterns: list[Any]
    processed_entities: list[dict[str, Any]]
    post_processing_trace: list[dict[str, Any]]
    errors: list[str]


def _resolve_local_patterns(state: PostProcessingState) -> list[Any]:
    """Use injected patterns, else load active package patterns for org_id."""
    injected = state.get("local_concept_patterns")
    if injected is not None:
        return list(injected or [])
    org_id = str(state.get("org_id") or "").strip() or None
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient
        from libs.ner.local_concept_recovery import load_active_package_patterns

        client = KnowledgeGraphClient()
        try:
            return load_active_package_patterns(client, org_id)
        finally:
            client.close()
    except Exception:
        logger.debug("active local package pattern load skipped", exc_info=True)
        return []


def run_post_process(state: PostProcessingState) -> dict[str, Any]:
    errors = list(state.get("errors") or [])
    try:
        from libs.ner.post_processor_rules import parse_rules
        from libs.pipeline.post_processing import run_post_processing_with_trace

        encounter_text = state.get("encounter_text") or ""
        entities = state.get("entities") or []
        raw_rules = state.get("rules") or []
        enable_disorder_gate = state.get("enable_disorder_gate", False)
        coding_mode = state.get("coding_mode", "hitl")
        rules = parse_rules(raw_rules) if raw_rules else None
        patterns = _resolve_local_patterns(state)
        processed, layer_trace = run_post_processing_with_trace(
            encounter_text,
            entities,
            rules=rules,
            enable_disorder_gate=enable_disorder_gate,
            coding_mode=coding_mode,
            local_concept_patterns=patterns,
        )
        return {
            "entities": processed,
            "processed_entities": processed,
            "post_processing_trace": layer_trace,
            "errors": errors,
        }
    except ImportError as e:
        logger.warning("Post-processing module unavailable: %s", e)
        errors.append(f"post_processing: {e}")
        return {
            "entities": state.get("entities", []),
            "processed_entities": state.get("entities", []),
            "post_processing_trace": [
                {
                    "layer_id": "post_processing",
                    "name": "Post-processing",
                    "status": "error",
                    "error": str(e),
                    "before_count": len(state.get("entities", []) or []),
                    "after_count": len(state.get("entities", []) or []),
                    "added_count": 0,
                    "removed_count": 0,
                    "updated_count": 0,
                    "duration_ms": 0,
                }
            ],
            "errors": errors,
        }
    except Exception as e:
        logger.exception("Post-processing failed")
        errors.append(f"post_processing: {e}")
        return {
            "entities": state.get("entities", []),
            "processed_entities": state.get("entities", []),
            "post_processing_trace": [
                {
                    "layer_id": "post_processing",
                    "name": "Post-processing",
                    "status": "error",
                    "error": str(e),
                    "before_count": len(state.get("entities", []) or []),
                    "after_count": len(state.get("entities", []) or []),
                    "added_count": 0,
                    "removed_count": 0,
                    "updated_count": 0,
                    "duration_ms": 0,
                }
            ],
            "errors": errors,
        }


def build_post_processing_subgraph() -> CompiledStateGraph:
    g = StateGraph(PostProcessingState)
    g.add_node("run_post_process", run_post_process)
    g.add_edge(START, "run_post_process")
    g.add_edge("run_post_process", END)
    return g.compile()
