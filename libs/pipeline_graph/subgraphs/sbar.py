"""SBAR generation subgraph (legacy heuristic).

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")

This subgraph is kept for the pipeline canvas test-runs that wire SBAR
in as a step. The PRODUCTION SBAR flow is the dedicated pub/sub
orchestrator -- see ``services.pipeline_worker.app.services.sbar_orchestrator``
and DI-LEO-AI-186. Use ``POST /sbar/jobs`` to trigger a real run.

Prompt resolution:
1. ``prompt_configs`` list in state (from Neo4j PromptConfig nodes)
2. ``libs.prompts.registry`` (Neo4j -- hardcoded fallback)
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class SBARState(TypedDict, total=False):
    patient_id: str
    referral_id: str
    patient_context: list[dict[str, Any]]
    prompt_configs: list[dict[str, Any]]
    sbar_report: dict[str, Any]
    sbar_sections: dict[str, str]
    extracted: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    safety_net_alerts: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    errors: list[str]


def _resolve_sbar_prompts(state: SBARState) -> dict[str, str]:
    """Return a dict of prompt name → text for SBAR generation.

    Checks state.prompt_configs first, then falls back to the registry
    for the episode_builder_system prompt.
    """
    configs = state.get("prompt_configs") or []
    result: dict[str, str] = {}
    for cfg in configs:
        if cfg.get("systemPrompt"):
            result[cfg.get("name", "custom")] = cfg["systemPrompt"]
    if not result:
        try:
            from libs.prompts.registry import get_prompt

            result["episode_builder_system"] = get_prompt("episode_builder_system", 1)
        except (KeyError, ImportError, RuntimeError):
            logger.warning("Falling back to default SBAR prompts: registry unavailable")
    return result


def generate_sbar(state: SBARState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    prompts = _resolve_sbar_prompts(state)
    logger.info(
        "Generating SBAR for patient %s with %d prompt(s)",
        patient_id,
        len(prompts),
    )
    entities = list(state.get("entities") or state.get("extracted") or [])
    recommendations = list(state.get("recommendations") or [])
    alerts = list(state.get("safety_net_alerts") or [])

    situation = (
        ", ".join(
            str(entity.get("text") or entity.get("concept_name") or "").strip()
            for entity in entities[:3]
            if str(entity.get("text") or entity.get("concept_name") or "").strip()
        )
        or "No key findings supplied."
    )
    background = (
        f"Patient {patient_id} with {len(entities)} extracted clinical finding(s)."
    )
    assessment = f"{len(alerts)} safety-net alert(s); {len(recommendations)} recommendation(s) generated."
    recommendation = (
        str(recommendations[0].get("action"))
        if recommendations
        else "Review patient context and continue routine monitoring."
    )
    return {
        "sbar_report": {
            "situation": situation,
            "background": background,
            "assessment": assessment,
            "recommendation": recommendation,
            "prompt_count": len(prompts),
        },
        "sbar_sections": {
            "situation": situation,
            "background": background,
            "assessment": assessment,
            "recommendation": recommendation,
        },
        "extracted": entities,
        "errors": list(state.get("errors") or []),
    }


def build_sbar_subgraph() -> CompiledStateGraph:
    g = StateGraph(SBARState)
    g.add_node("generate_sbar", generate_sbar)
    g.add_edge(START, "generate_sbar")
    g.add_edge("generate_sbar", END)
    return g.compile()
