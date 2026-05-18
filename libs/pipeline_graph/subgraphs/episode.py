"""Episode building subgraph.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult
from services.analysis_worker.app.analyzers.episode_builder import (
    build_episodes as build_patient_episodes,
)
from libs.pipeline_graph.subgraphs.staging_enrichment import (
    enrich_staging as run_stage_enrichment,
)

logger = logging.getLogger(__name__)


class EpisodeState(TypedDict, total=False):
    patient_id: str
    org_id: str
    domain_id: str
    anchors: list[dict[str, Any]]
    anchor_result: dict[str, Any]
    episodes: list[dict[str, Any]]
    episode_ids: list[str]
    errors: list[str]


def _to_anchor_result(state: EpisodeState) -> AnchorResult:
    anchor_result = state.get("anchor_result") or {}
    if anchor_result:
        return AnchorResult(
            patient_id=str(state.get("patient_id") or ""),
            referral_anchors=list(anchor_result.get("referral_anchors") or []),
            diagnosis_anchors=list(anchor_result.get("diagnosis_anchors") or []),
            treatment_anchors=list(anchor_result.get("treatment_anchors") or []),
            specialist_visit_anchors=list(
                anchor_result.get("specialist_visit_anchors") or []
            ),
            benign_closure_anchors=list(
                anchor_result.get("benign_closure_anchors") or []
            ),
            specialist_outcome_letter_anchors=list(
                anchor_result.get("specialist_outcome_letter_anchors") or []
            ),
            first_presentation_anchors=list(
                anchor_result.get("first_presentation_anchors") or []
            ),
        )
    anchors = list(state.get("anchors") or [])
    return AnchorResult(
        patient_id=str(state.get("patient_id") or ""),
        referral_anchors=[a for a in anchors if a.get("milestone_type") == "referral"],
        diagnosis_anchors=[
            a for a in anchors if a.get("milestone_type") == "diagnosis"
        ],
        treatment_anchors=[
            a for a in anchors if a.get("milestone_type") == "treatment_start"
        ],
        specialist_visit_anchors=[
            a for a in anchors if a.get("milestone_type") == "specialist_visit"
        ],
        benign_closure_anchors=[
            a for a in anchors if a.get("milestone_type") == "benign_closure"
        ],
        specialist_outcome_letter_anchors=[
            a for a in anchors if a.get("milestone_type") == "specialist_outcome_letter"
        ],
        first_presentation_anchors=[
            a for a in anchors if a.get("milestone_type") == "first_presentation"
        ],
    )


def _run_coro_sync(coro_factory):
    """Run a coroutine from sync code, even if an event loop is active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro_factory())).result()


def build_episodes(state: EpisodeState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    logger.info("Building episodes for patient %s", patient_id)
    errors = list(state.get("errors") or [])

    domain_id = state.get("domain_id") or ""

    def _build():
        async def _inner():
            from libs.neo4j_client.client import PatientGraphClient

            client = PatientGraphClient()
            try:
                return await build_patient_episodes(
                    patient_id=patient_id,
                    anchors=_to_anchor_result(state),
                    patient_client=client,
                    domain_id=domain_id,
                )
            finally:
                client.close()

        return _inner()

    try:
        result = _run_coro_sync(_build)
    except Exception:
        logger.exception(
            "Episode build failed for patient %s -- propagating error",
            patient_id,
        )
        raise

    episodes = [
        {
            "episode_id": episode_id,
            "patient_id": patient_id,
        }
        for episode_id in result.episode_ids
    ]
    return {
        "episodes": episodes,
        "episode_ids": result.episode_ids,
        "errors": errors + list(result.errors),
    }


def build_episode_subgraph() -> CompiledStateGraph:
    g = StateGraph(EpisodeState)
    g.add_node("build_episodes", build_episodes)
    g.add_node("staging_enrichment", run_stage_enrichment)
    g.add_edge(START, "build_episodes")
    g.add_edge("build_episodes", "staging_enrichment")
    g.add_edge("staging_enrichment", END)
    return g.compile()
