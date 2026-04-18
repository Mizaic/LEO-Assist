"""Haiku-driven episode engine.

Replaces the rule-based ``anchor_detector`` + ``episode_builder``.

Design:
    timeline_loader -> segmenter -> classifier -> milestone_extractor
                    -> reconciler -> writer

Each agent stage is a Haiku (or Sonnet for the reconciler) call that returns
structured JSON via Bedrock ``tool_config``. Every milestone cites an
encounter_id and an evidence quote. Every run records a trace for audit.

Public API:
    run_episode_engine(patient_id) -> EpisodeEngineResult

Used by:
    - libs/pipeline_graph/subgraphs/episode_engine.py (LangGraph subgraph
      registered as ``episode_engine``)
    - scripts/investigations/episode_engine_spike/run_spike.py
    - scripts/_wipe_episodes_and_rebuild.py (post-cutover)
"""

from __future__ import annotations

from services.analysis_worker.app.episode_engine.chain import (
    EpisodeEngineResult,
    run_episode_engine,
)

__all__ = [
    "EpisodeEngineResult",
    "run_episode_engine",
]
