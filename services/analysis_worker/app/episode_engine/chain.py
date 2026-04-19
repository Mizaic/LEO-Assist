"""LangGraph chain orchestrating the Haiku episode engine.

Stages:
    1. timeline_loader  (deterministic, Neo4j read)
    2. segmenter        (Haiku, tool-call -> SegmenterResult)
    3. classifier       (Haiku, fan-out per window)
    4. milestone_extractor (Haiku, fan-out per cancer-ish window)
    5. reconciler       (Haiku/Sonnet, all candidates -> final episodes)
    6. writer           (deterministic, Neo4j write or dry-run)

Public entry points:
    - build_episode_engine_subgraph() -> CompiledStateGraph
        For registration in libs/pipeline_graph/registry.py.
    - run_episode_engine(patient_id, ...) -> EpisodeEngineResult
        Convenience sync wrapper used by spike + cutover scripts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.factory import LLMClient, create_llm
from libs.neo4j_client.client import PatientGraphClient
from services.analysis_worker.app.episode_engine.agents import (
    classifier as classifier_agent,
    milestone_extractor as milestone_agent,
    reconciler as reconciler_agent,
    segmenter as segmenter_agent,
)
from services.analysis_worker.app.episode_engine.agents._common import StageError
from services.analysis_worker.app.episode_engine.schemas import (
    Episode,
    Milestone,
    ReconciledEpisode,
    StageTrace,
)
from services.analysis_worker.app.episode_engine.state import EngineState
from services.analysis_worker.app.episode_engine.timeline_loader import load_timeline
from services.analysis_worker.app.episode_engine.tracing import (
    build_provenance,
    new_trace_id,
    persist_trace,
)
from services.analysis_worker.app.episode_engine.writer import write_episodes

logger = logging.getLogger(__name__)


# Episode types that trigger milestone extraction
_EXTRACT_EPISODE_TYPES = {"cancer", "multi_site", "benign"}
# Drop windows below this confidence
_CLASSIFIER_MIN_CONFIDENCE = 0.4


# -- Result wrapper -------------------------------------------------------


@dataclass
class EpisodeEngineResult:
    """High-level result from a single patient run."""

    patient_id: str
    episodes: list[Episode]
    stage_traces: list[StageTrace]
    errors: list[str] = field(default_factory=list)
    trace_id: str = ""
    encounter_count: int = 0
    dry_run: bool = False

    @property
    def episode_count(self) -> int:
        return len(self.episodes)

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.stage_traces)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.stage_traces)

    @property
    def total_cached_input_tokens(self) -> int:
        return sum(s.cached_input_tokens for s in self.stage_traces)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(s.cost_usd for s in self.stage_traces), 6)

    @property
    def total_latency_ms(self) -> int:
        return sum(s.latency_ms for s in self.stage_traces)


# -- Per-stage node functions --------------------------------------------


def _node_load_timeline(state: EngineState) -> dict[str, Any]:
    patient_id = str(state.get("patient_id") or "")
    client = PatientGraphClient()
    try:
        trunk, index, count = load_timeline(patient_id, client=client)
    finally:
        client.close()
    return {
        "timeline_text": trunk,
        "encounter_index": index,
        "encounter_count": count,
    }


def _node_segmenter(state: EngineState) -> dict[str, Any]:
    timeline_text = state.get("timeline_text") or ""
    if not timeline_text:
        return {"candidate_windows": [], "stage_traces": _append_trace(state, None)}

    llm = _llm("small")
    try:
        result, trace = segmenter_agent.run(
            llm=llm,
            patient_id=str(state.get("patient_id") or ""),
            timeline_text=timeline_text,
        )
    except StageError as exc:
        return {
            "candidate_windows": [],
            "errors": list(state.get("errors") or []) + [f"segmenter: {exc}"],
            "stage_traces": _append_trace(state, _failed_trace("segmenter", str(exc))),
        }

    return {
        "candidate_windows": [w.model_dump(mode="json") for w in result.windows],
        "stage_traces": _append_trace(state, trace),
    }


def _node_classifier(state: EngineState) -> dict[str, Any]:
    candidates = state.get("candidate_windows") or []
    if not candidates:
        return {"classified_windows": []}

    llm = _llm("small")
    classified: list[dict[str, Any]] = []
    new_traces: list[StageTrace] = []
    errors: list[str] = list(state.get("errors") or [])

    for window in candidates:
        window_text = _slice_window_trunk(state, window)
        try:
            result, trace = classifier_agent.run(
                llm=llm,
                patient_id=str(state.get("patient_id") or ""),
                window_id=window.get("window_id", ""),
                suspected_site=window.get("suspected_site", "unknown"),
                window_start=str(window.get("window_start", "")),
                window_end=str(window.get("window_end") or ""),
                window_text=window_text,
            )
            classified.append(result.model_dump(mode="json"))
            new_traces.append(trace)
        except StageError as exc:
            errors.append(f"classifier[{window.get('window_id')}]: {exc}")
            new_traces.append(
                _failed_trace("classifier", str(exc))
            )

    return {
        "classified_windows": classified,
        "errors": errors,
        "stage_traces": list(state.get("stage_traces") or [])
        + [t.model_dump() for t in new_traces],
    }


def _node_milestone_extractor(state: EngineState) -> dict[str, Any]:
    candidates_by_id = {
        w.get("window_id"): w for w in (state.get("candidate_windows") or [])
    }
    classified = state.get("classified_windows") or []
    encounter_index = state.get("encounter_index") or {}

    llm = _llm("small")
    extracted: list[dict[str, Any]] = []
    new_traces: list[StageTrace] = []
    errors: list[str] = list(state.get("errors") or [])

    for cls in classified:
        if cls.get("episode_type") not in _EXTRACT_EPISODE_TYPES:
            continue
        if float(cls.get("confidence") or 0.0) < _CLASSIFIER_MIN_CONFIDENCE:
            continue

        window = candidates_by_id.get(cls.get("window_id")) or {}
        window_full = _slice_window_full(window, encounter_index)
        if not window_full.strip():
            continue

        try:
            result, trace = milestone_agent.run(
                llm=llm,
                patient_id=str(state.get("patient_id") or ""),
                window_id=cls.get("window_id", ""),
                suspected_site=window.get("suspected_site", "unknown"),
                window_start=str(window.get("window_start", "")),
                window_end=str(window.get("window_end") or ""),
                window_full_text=window_full,
            )
            extracted.append(result.model_dump(mode="json"))
            new_traces.append(trace)
        except StageError as exc:
            errors.append(f"milestone[{cls.get('window_id')}]: {exc}")
            new_traces.append(_failed_trace("milestone_extractor", str(exc)))

    return {
        "extracted": extracted,
        "errors": errors,
        "stage_traces": list(state.get("stage_traces") or [])
        + [t.model_dump() for t in new_traces],
    }


def _node_reconciler(state: EngineState) -> dict[str, Any]:
    classified_by_id = {
        c.get("window_id"): c for c in (state.get("classified_windows") or [])
    }
    candidates_by_id = {
        w.get("window_id"): w for w in (state.get("candidate_windows") or [])
    }
    extracted_by_id = {
        e.get("window_id"): e for e in (state.get("extracted") or [])
    }

    payload: list[dict[str, Any]] = []
    for window_id, cls in classified_by_id.items():
        window = candidates_by_id.get(window_id) or {}
        ext = extracted_by_id.get(window_id) or {}
        payload.append(
            {
                "window_id": window_id,
                "suspected_site": window.get("suspected_site", "unknown"),
                "window_start": window.get("window_start"),
                "window_end": window.get("window_end"),
                "episode_type": cls.get("episode_type"),
                "classifier_confidence": cls.get("confidence"),
                "classifier_reasoning": cls.get("reasoning"),
                "milestones": ext.get("milestones") or [],
                "milestone_review_flag": ext.get("needs_human_review", False),
            }
        )

    if not payload:
        return {"reconciled_episodes": []}

    llm = _llm("big")  # reconciler benefits from Sonnet's reasoning
    try:
        result, trace = reconciler_agent.run(
            llm=llm,
            patient_id=str(state.get("patient_id") or ""),
            candidates=payload,
        )
    except StageError as exc:
        return {
            "reconciled_episodes": [],
            "errors": list(state.get("errors") or []) + [f"reconciler: {exc}"],
            "stage_traces": _append_trace(state, _failed_trace("reconciler", str(exc))),
        }

    return {
        "reconciled_episodes": [ep.model_dump(mode="json") for ep in result.episodes],
        "stage_traces": _append_trace(state, trace),
    }


def _node_writer(state: EngineState) -> dict[str, Any]:
    patient_id = str(state.get("patient_id") or "")
    domain_id = str(state.get("domain_id") or "")
    dry_run = bool(state.get("dry_run") or False)
    reconciled_dicts = state.get("reconciled_episodes") or []

    episodes: list[ReconciledEpisode] = []
    for raw in reconciled_dicts:
        try:
            episodes.append(ReconciledEpisode.model_validate(raw))
        except Exception as exc:
            logger.warning(
                "writer: dropping invalid reconciled episode for %s: %s",
                patient_id,
                exc,
            )

    trace_id = state.get("trace_id") or new_trace_id()
    stage_dicts = state.get("stage_traces") or []
    stage_traces = [StageTrace.model_validate(d) for d in stage_dicts]
    provenance = build_provenance(
        trace_id=trace_id,
        stages=stage_traces,
        encounter_count=int(state.get("encounter_count") or 0),
    )

    upstream_errors = list(state.get("errors") or [])
    has_upstream_errors = bool(upstream_errors)

    client = PatientGraphClient()
    try:
        if has_upstream_errors:
            logger.warning(
                "writer: SKIPPING delete+write for patient %s because "
                "upstream stages reported errors (%d). Existing "
                "EpisodeOfCare nodes are preserved. Errors: %s",
                patient_id,
                len(upstream_errors),
                upstream_errors,
            )
            materialised = []
        else:
            materialised = write_episodes(
                client=client,
                patient_id=patient_id,
                domain_id=domain_id,
                episodes=episodes,
                provenance=provenance,
                dry_run=dry_run,
            )
        persist_trace(
            client=client,
            trace_id=trace_id,
            patient_id=patient_id,
            stages=stage_traces,
            encounter_count=int(state.get("encounter_count") or 0),
            episode_count=len(materialised),
            errors=upstream_errors,
            dry_run=dry_run,
        )
    finally:
        client.close()

    return {
        "written_episodes": [e.model_dump(mode="json") for e in materialised],
        "trace_id": trace_id,
    }


# -- Helpers --------------------------------------------------------------


def _llm(tier: str) -> LLMClient:
    return create_llm(provider="aws", tier=tier)


def _append_trace(state: EngineState, trace: StageTrace | None) -> list[dict]:
    base = list(state.get("stage_traces") or [])
    if trace is None:
        return base
    base.append(trace.model_dump())
    return base


def _failed_trace(stage: str, error: str) -> StageTrace:
    return StageTrace(
        stage=stage,
        prompt_version="v1",
        model_id="unknown",
        ok=False,
        error=error[:500],
    )


_DATE_HEADER_RX = re.compile(r"^== (\d{4}-\d{2}-\d{2}) \((\d+) record")


def _slice_window_trunk(
    state: EngineState, window: dict[str, Any]
) -> str:
    """Return the trunk-view text for dates within the candidate window."""
    timeline_text = state.get("timeline_text") or ""
    start = str(window.get("window_start", "0000-00-00"))
    end = str(window.get("window_end") or "9999-12-31")

    out: list[str] = []
    keep = False
    for line in timeline_text.splitlines():
        m = _DATE_HEADER_RX.match(line)
        if m:
            d = m.group(1)
            keep = start <= d <= end
        if keep:
            out.append(line)
    return "\n".join(out)


def _slice_window_full(
    window: dict[str, Any],
    encounter_index: dict[str, dict[str, Any]],
) -> str:
    """Return per-encounter full snippets for all encounters within the
    candidate window. Format: ``[encounter_id] date :: full_snippet``."""
    start = str(window.get("window_start", "0000-00-00"))
    end = str(window.get("window_end") or "9999-12-31")

    in_window = [
        rec
        for rec in encounter_index.values()
        if rec.get("date") and start <= str(rec["date"]) <= end
    ]
    in_window.sort(key=lambda r: (str(r.get("date", "")), r.get("encounter_id", "")))

    blocks: list[str] = []
    for rec in in_window:
        blocks.append(
            "[{eid}] {d}\n{snippet}".format(
                eid=rec["encounter_id"],
                d=rec.get("date"),
                snippet=rec.get("full_snippet", ""),
            )
        )
    return "\n\n".join(blocks)


# -- Compiled subgraph + sync runner --------------------------------------


def build_episode_engine_subgraph() -> CompiledStateGraph:
    """Compile the episode-engine LangGraph subgraph."""
    g = StateGraph(EngineState)
    g.add_node("load_timeline", _node_load_timeline)
    g.add_node("segmenter", _node_segmenter)
    g.add_node("classifier", _node_classifier)
    g.add_node("milestone_extractor", _node_milestone_extractor)
    g.add_node("reconciler", _node_reconciler)
    g.add_node("writer", _node_writer)

    g.add_edge(START, "load_timeline")
    g.add_edge("load_timeline", "segmenter")
    g.add_edge("segmenter", "classifier")
    g.add_edge("classifier", "milestone_extractor")
    g.add_edge("milestone_extractor", "reconciler")
    g.add_edge("reconciler", "writer")
    g.add_edge("writer", END)

    return g.compile()


def run_episode_engine(
    patient_id: str,
    *,
    domain_id: str = "",
    dry_run: bool = False,
) -> EpisodeEngineResult:
    """Run the engine for one patient (sync wrapper for scripts/spike)."""

    graph = build_episode_engine_subgraph()
    initial: EngineState = {
        "patient_id": str(patient_id),
        "domain_id": domain_id,
        "dry_run": dry_run,
        "stage_traces": [],
        "errors": [],
        "trace_id": new_trace_id(),
    }
    final = graph.invoke(initial)

    written = final.get("written_episodes") or []
    episodes: list[Episode] = []
    for raw in written:
        try:
            episodes.append(Episode.model_validate(raw))
        except Exception as exc:
            logger.warning("Could not validate written episode: %s", exc)

    stages = [
        StageTrace.model_validate(d) for d in (final.get("stage_traces") or [])
    ]
    return EpisodeEngineResult(
        patient_id=str(patient_id),
        episodes=episodes,
        stage_traces=stages,
        errors=list(final.get("errors") or []),
        trace_id=str(final.get("trace_id") or ""),
        encounter_count=int(final.get("encounter_count") or 0),
        dry_run=dry_run,
    )


# Export Milestone for downstream typing without repeating the import path
__all__ = [
    "EpisodeEngineResult",
    "Milestone",
    "build_episode_engine_subgraph",
    "run_episode_engine",
]
