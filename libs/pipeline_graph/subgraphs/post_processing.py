"""Post-processing subgraph wrapping the canonical 9-layer pipeline."""

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
    processed_entities: list[dict[str, Any]]
    errors: list[str]


def run_post_process(state: PostProcessingState) -> dict[str, Any]:
    errors = list(state.get("errors") or [])
    try:
        from libs.ner.post_processor_rules import parse_rules
        from libs.pipeline.post_processing import run_post_processing

        encounter_text = state.get("encounter_text") or ""
        entities = state.get("entities") or []
        raw_rules = state.get("rules") or []
        enable_disorder_gate = state.get("enable_disorder_gate", False)
        coding_mode = state.get("coding_mode", "hitl")
        rules = parse_rules(raw_rules) if raw_rules else None
        processed = run_post_processing(
            encounter_text,
            entities,
            rules=rules,
            enable_disorder_gate=enable_disorder_gate,
            coding_mode=coding_mode,
        )
        return {"entities": processed, "processed_entities": processed, "errors": errors}
    except ImportError as e:
        logger.warning("Post-processing module unavailable: %s", e)
        errors.append(f"post_processing: {e}")
        return {"entities": state.get("entities", []), "processed_entities": state.get("entities", []), "errors": errors}
    except Exception as e:
        logger.exception("Post-processing failed")
        errors.append(f"post_processing: {e}")
        return {"entities": state.get("entities", []), "processed_entities": state.get("entities", []), "errors": errors}


def build_post_processing_subgraph() -> CompiledStateGraph:
    g = StateGraph(PostProcessingState)
    g.add_node("run_post_process", run_post_process)
    g.add_edge(START, "run_post_process")
    g.add_edge("run_post_process", END)
    return g.compile()
