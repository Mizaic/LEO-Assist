"""LangGraph state for the episode engine chain."""

from __future__ import annotations

from typing import Any, TypedDict


class EngineState(TypedDict, total=False):
    """Per-patient state carried between chain stages.

    All optional so each node can write only its own slice. Downstream nodes
    that need an upstream output should raise loudly if it's missing.
    """

    # -- Inputs ------------------------------------------------------------
    patient_id: str
    domain_id: str

    # -- Stage 1: timeline_loader ------------------------------------------
    timeline_text: str          # compact, prompt-ready
    encounter_index: dict[str, dict[str, Any]]  # encounter_id -> raw row
    encounter_count: int

    # -- Stage 2: segmenter ------------------------------------------------
    candidate_windows: list[dict[str, Any]]   # CandidateWindow dicts

    # -- Stage 3: classifier (per-window) ----------------------------------
    classified_windows: list[dict[str, Any]]  # ClassifierResult dicts

    # -- Stage 4: milestone_extractor (per cancer-ish window) --------------
    extracted: list[dict[str, Any]]           # MilestoneExtractorResult dicts

    # -- Stage 5: reconciler -----------------------------------------------
    reconciled_episodes: list[dict[str, Any]]  # ReconciledEpisode dicts

    # -- Stage 6: writer (final) -------------------------------------------
    written_episodes: list[dict[str, Any]]     # Episode dicts (post-write)

    # -- Provenance / control ---------------------------------------------
    trace_id: str
    stage_traces: list[dict[str, Any]]         # StageTrace dicts
    errors: list[str]
    dry_run: bool                              # if True, writer skips graph mutations
