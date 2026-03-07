"""Episode building subgraph placeholder. Wraps analysis_worker episode logic when pipeline_worker is built."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class EpisodeState(TypedDict, total=False):
    patient_id: str
    org_id: str
    anchors: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    errors: list[str]


def build_episodes(state: EpisodeState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Building episodes for patient %s", patient_id)
    return {"episodes": [], "errors": list(state.get("errors") or [])}


def build_episode_subgraph() -> CompiledStateGraph:
    g = StateGraph(EpisodeState)
    g.add_node("build_episodes", build_episodes)
    g.add_edge(START, "build_episodes")
    g.add_edge("build_episodes", END)
    return g.compile()
