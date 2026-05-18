"""LangGraph subgraph wrapper for the Haiku episode engine.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")

Registered as ``episode_engine`` in
``libs/pipeline_graph/registry.py``. The engine itself lives in
``services.analysis_worker.app.episode_engine.chain``.
"""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from services.analysis_worker.app.episode_engine.chain import (
    build_episode_engine_subgraph,
)


def build_episode_engine_pipeline_subgraph() -> CompiledStateGraph:
    return build_episode_engine_subgraph()


__all__ = ["build_episode_engine_pipeline_subgraph"]
