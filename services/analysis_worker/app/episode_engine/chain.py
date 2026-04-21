"""LangGraph chain orchestrating the Haiku episode engine.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

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
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.llm_client.factory import LLMClient, create_llm
from libs.neo4j_client.client import PatientGraphClient
from services.analysis_worker.app.episode_engine.agents import (
    audit_relevance_filter as audit_filter_agent,
    classifier as classifier_agent,
    milestone_extractor as milestone_agent,
    reconciler as reconciler_agent,
    segmenter as segmenter_agent,
)
from services.analysis_worker.app.episode_engine.agents._common import StageError
from services.analysis_worker.app.episode_engine.schemas import (
    AuditFilterDrop,
    Episode,
    EpisodeOfCareTrace,
    FocusedSet,
    Milestone,
    MilestoneExtractorResult,
    PartTrace,
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
from services.analysis_worker.app.episode_engine.window_partitioner import (
    merge_milestones_deterministic,
    partition_window,
)
from services.analysis_worker.app.episode_engine.writer import write_episodes

logger = logging.getLogger(__name__)


# Episode types that trigger milestone extraction
_EXTRACT_EPISODE_TYPES = {"cancer", "multi_site", "benign"}
# Drop windows below this confidence
_CLASSIFIER_MIN_CONFIDENCE = 0.4


def _candidate_parallelism() -> int:
    """Bounded parallelism for per-window LLM fan-out.

    Each candidate window is an independent Anthropic call. Running them
    sequentially turns a 5-window patient into 5x latency. Cap at 8 by
    default to avoid hammering the upstream model rate limit; tunable
    via ``EPISODE_ENGINE_CANDIDATE_PARALLELISM``.
    """
    try:
        return max(1, int(os.getenv("EPISODE_ENGINE_CANDIDATE_PARALLELISM", "8")))
    except (TypeError, ValueError):
        return 8


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
    new_traces: list[StageTrace] = []
    errors: list[str] = list(state.get("errors") or [])

    def _classify_one(window: dict[str, Any]) -> tuple[
        dict[str, Any] | None, StageTrace | None, str | None
    ]:
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
            return result.model_dump(mode="json"), trace, None
        except StageError as exc:
            return None, _failed_trace("classifier", str(exc)), (
                f"classifier[{window.get('window_id')}]: {exc}"
            )

    classified: list[dict[str, Any]] = []
    max_workers = min(_candidate_parallelism(), len(candidates))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for cls, trace, err in pool.map(_classify_one, candidates):
            if cls is not None:
                classified.append(cls)
            if trace is not None:
                new_traces.append(trace)
            if err is not None:
                errors.append(err)

    return {
        "classified_windows": classified,
        "errors": errors,
        "stage_traces": list(state.get("stage_traces") or [])
        + [t.model_dump() for t in new_traces],
    }


def _node_audit_relevance_filter(state: EngineState) -> dict[str, Any]:
    """Stage 3.5: build a focused encounter set per cancer-ish window.

    See DI-LEO-AI-524. The focused set is the union of the deterministic
    always-keep guards and the Haiku batched relevance triage. On Haiku
    error the filter fails open (every encounter in the failed batch
    flows through with kept_by_fallback = true) so a transient outage
    never silently turns an encounter into a missing milestone.
    """
    candidates_by_id = {
        w.get("window_id"): w for w in (state.get("candidate_windows") or [])
    }
    classified = state.get("classified_windows") or []
    encounter_index = state.get("encounter_index") or {}

    llm = _llm("small")
    focused_sets: dict[str, dict[str, Any]] = dict(state.get("focused_sets") or {})
    new_traces: list[StageTrace] = []
    errors: list[str] = list(state.get("errors") or [])

    eligible: list[dict[str, Any]] = []
    for cls in classified:
        if cls.get("episode_type") not in _EXTRACT_EPISODE_TYPES:
            continue
        if float(cls.get("confidence") or 0.0) < _CLASSIFIER_MIN_CONFIDENCE:
            continue
        window_id = cls.get("window_id", "")
        window = candidates_by_id.get(window_id) or {}
        in_window = _encounters_in_window(window, encounter_index)
        if not in_window:
            continue
        eligible.append(
            {
                "window_id": window_id,
                "window": window,
                "in_window": in_window,
                "hint_ids": _hint_flagged_ids(in_window),
            }
        )

    def _filter_one(item: dict[str, Any]) -> tuple[
        str, dict[str, Any] | None, list[StageTrace], str | None
    ]:
        window_id = item["window_id"]
        window = item["window"]
        try:
            focused, traces = audit_filter_agent.run(
                llm=llm,
                patient_id=str(state.get("patient_id") or ""),
                window_id=window_id,
                suspected_site=window.get("suspected_site", "unknown"),
                encounters=item["in_window"],
                segmenter_anchors=window.get("anchors") or {},
                cancer_coded_encounter_ids=window.get(
                    "cancer_coded_encounter_ids"
                )
                or [],
                hint_flagged_encounter_ids=item["hint_ids"],
            )
            return window_id, focused.model_dump(mode="json"), list(traces), None
        except Exception as exc:  # pragma: no cover - guarded by audit_filter
            return (
                window_id,
                None,
                [_failed_trace("audit_relevance_filter", str(exc))],
                f"audit_relevance_filter[{window_id}]: {exc}",
            )

    if eligible:
        max_workers = min(_candidate_parallelism(), len(eligible))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for window_id, dump, traces, err in pool.map(_filter_one, eligible):
                if dump is not None:
                    focused_sets[window_id] = dump
                if traces:
                    new_traces.extend(traces)
                if err is not None:
                    errors.append(err)

    return {
        "focused_sets": focused_sets,
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
    focused_sets = state.get("focused_sets") or {}

    llm = _llm("small")
    extracted: list[dict[str, Any]] = []
    eoc_traces: list[dict[str, Any]] = list(state.get("eoc_traces") or [])
    new_traces: list[StageTrace] = []
    errors: list[str] = list(state.get("errors") or [])

    def _extract_one(cls: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single classifier window and return per-window output.

        Returns a dict with keys: extracted (dict|None), eoc_trace
        (dict|None), traces (list), errors (list). Returns None if the
        window should be skipped silently.
        """
        if cls.get("episode_type") not in _EXTRACT_EPISODE_TYPES:
            return None
        if float(cls.get("confidence") or 0.0) < _CLASSIFIER_MIN_CONFIDENCE:
            return None

        window_id = cls.get("window_id", "")
        window = candidates_by_id.get(window_id) or {}

        focused_dict = focused_sets.get(window_id) or {}
        focused = (
            FocusedSet.model_validate(focused_dict)
            if focused_dict
            else _focused_from_window(window, encounter_index)
        )
        focused_encounters = [
            encounter_index.get(fe.encounter_id, {})
            | {
                "encounter_id": fe.encounter_id,
                "date": (
                    str(fe.encounter_date) if fe.encounter_date is not None else ""
                ),
            }
            for fe in focused.encounters
        ]
        focused_encounters = [
            e for e in focused_encounters if e.get("encounter_id")
        ]
        if not focused_encounters:
            return None

        local_errors: list[str] = []
        local_traces: list[StageTrace] = []

        partitions, partition_report = partition_window(focused_encounters)
        if partition_report.too_many_parts:
            local_errors.append(
                f"milestone[{window_id}]: audit_partition_overflow "
                f"({partition_report.notice or 'too many parts'})"
            )
            return {
                "extracted": MilestoneExtractorResult(
                    window_id=window_id,
                    milestones=[],
                    needs_human_review=True,
                    reasoning=(
                        partition_report.notice
                        or (
                            "Audit Partition Overflow: this window has too "
                            "much pathway-relevant material to audit in "
                            "one run. Ask a clinician to review."
                        )
                    ),
                ).model_dump(mode="json"),
                "eoc_trace": _build_eoc_trace(
                    window_id=window_id,
                    focused=focused,
                    parts=[],
                    overflow=True,
                    audit_parts=0,
                ).model_dump(mode="json"),
                "traces": local_traces,
                "errors": local_errors,
            }

        per_part_results: list[MilestoneExtractorResult] = []
        part_traces: list[PartTrace] = []
        for part in partitions:
            part_full_text = _build_part_text(
                part=part,
                encounter_index=encounter_index,
            )
            try:
                result, trace = milestone_agent.run(
                    llm=llm,
                    patient_id=str(state.get("patient_id") or ""),
                    window_id=window_id,
                    suspected_site=window.get("suspected_site", "unknown"),
                    window_start=str(window.get("window_start", "")),
                    window_end=str(window.get("window_end") or ""),
                    window_full_text=part_full_text,
                )
                per_part_results.append(result)
                local_traces.append(trace)
                part_traces.append(
                    PartTrace(
                        part_index=part.index,
                        encounter_count=len(part.encounter_ids),
                        milestones_count=len(result.milestones),
                    )
                )
            except StageError as exc:
                local_errors.append(
                    f"milestone[{window_id} part {part.index}/{part.total}]: {exc}"
                )
                local_traces.append(
                    _failed_trace("milestone_extractor", str(exc))
                )
                per_part_results.append(
                    MilestoneExtractorResult(
                        window_id=window_id,
                        milestones=[],
                        needs_human_review=True,
                        reasoning=(
                            "This part failed to process; surviving parts "
                            "still contributed to the merged result."
                        ),
                    )
                )
                part_traces.append(
                    PartTrace(
                        part_index=part.index,
                        encounter_count=len(part.encounter_ids),
                        milestones_count=0,
                        error=str(exc)[:200],
                    )
                )

        merged = merge_milestones_deterministic(
            per_part_results, window_id=window_id
        )
        return {
            "extracted": merged.model_dump(mode="json"),
            "eoc_trace": _build_eoc_trace(
                window_id=window_id,
                focused=focused,
                parts=part_traces,
                overflow=False,
                audit_parts=len(partitions),
            ).model_dump(mode="json"),
            "traces": local_traces,
            "errors": local_errors,
        }

    if classified:
        max_workers = min(_candidate_parallelism(), len(classified))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for result in pool.map(_extract_one, classified):
                if result is None:
                    continue
                if result.get("extracted"):
                    extracted.append(result["extracted"])
                if result.get("eoc_trace"):
                    eoc_traces.append(result["eoc_trace"])
                new_traces.extend(result.get("traces") or [])
                errors.extend(result.get("errors") or [])

    return {
        "extracted": extracted,
        "eoc_traces": eoc_traces,
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


def _encounters_in_window(
    window: dict[str, Any],
    encounter_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the in-window encounter rows ordered by date then id."""
    start = str(window.get("window_start", "0000-00-00"))
    end = str(window.get("window_end") or "9999-12-31")
    rows = [
        rec
        for rec in encounter_index.values()
        if rec.get("date") and start <= str(rec["date"]) <= end
    ]
    rows.sort(key=lambda r: (str(r.get("date", "")), r.get("encounter_id", "")))
    return rows


def _hint_flagged_ids(in_window: list[dict[str, Any]]) -> list[str]:
    """Run the deterministic safety-netting / disruption hint detectors
    over the in-window encounters and return matched encounter ids.

    Mirrors ``_signal_hints`` but operates on the raw rows instead of the
    serialised window text, so the audit-relevance-filter guard layer
    can use the same vocabulary the milestone extractor relies on.
    """
    flagged: list[str] = []
    for rec in in_window:
        text = (rec.get("full_snippet") or rec.get("text") or "")
        cleaned = _ADMIN_NOISE_RX.sub(" ", str(text))
        if (
            _SAFETY_NETTING_HINT_RX.search(cleaned)
            or _DISRUPTION_HINT_RX.search(cleaned)
        ):
            eid = str(rec.get("encounter_id") or "")
            if eid:
                flagged.append(eid)
    return flagged


def _focused_from_window(
    window: dict[str, Any],
    encounter_index: dict[str, dict[str, Any]],
) -> FocusedSet:
    """Fallback FocusedSet when the audit filter did not run for a window.

    Treats every in-window encounter as kept_by_fallback so the milestone
    extractor still runs on the full window, preserving the
    no-encounter-silently-dropped invariant.
    """
    rows = _encounters_in_window(window, encounter_index)
    focused = FocusedSet.model_validate(
        {
            "encounters": [
                {
                    "encounter_id": str(r.get("encounter_id") or ""),
                    "encounter_date": (
                        r.get("date") if r.get("date") else None
                    ),
                    "kept_by_guard": False,
                    "kept_by_fallback": True,
                }
                for r in rows
                if r.get("encounter_id")
            ],
            "report": {
                "audit_input_encounters": len(rows),
                "audit_kept_by_guards": 0,
                "audit_kept_by_llm": 0,
                "audit_dropped_by_llm": [],
                "audit_filter_failed": True,
                "audit_filter_overflow": False,
                "audit_parts": 1,
            },
        }
    )
    return focused


def _build_part_text(
    *,
    part,
    encounter_index: dict[str, dict[str, Any]],
) -> str:
    """Render the per-encounter blocks for one Partition.

    Common case (single partition): byte-for-byte identical to the legacy
    ``_slice_window_full`` output for the encounters in that part.
    Multi-part runs: a leading ``Part i of N`` marker is added so the
    extractor knows it is summarising one slice of a wider audit; a
    ``part_in_encounter`` note is added for any record split across
    consecutive parts.
    """
    blocks: list[str] = []
    if part.total > 1:
        blocks.append(f"Part {part.index} of {part.total} of this audit window.")
    for eid in part.encounter_ids:
        rec = encounter_index.get(eid) or {}
        snippet = rec.get("full_snippet") or rec.get("text") or ""
        date = rec.get("date") or "unknown"
        header = f"[{eid}] {date}"
        if part.part_in_encounter and eid in part.part_in_encounter:
            i, n = part.part_in_encounter[eid]
            header += f" (record part {i} of {n})"
        blocks.append(f"{header}\n{snippet}")
    return "\n\n".join(blocks)


def _build_eoc_trace(
    *,
    window_id: str,
    focused: FocusedSet,
    parts: list[PartTrace],
    overflow: bool,
    audit_parts: int,
) -> EpisodeOfCareTrace:
    """Combine focus + partition signal into one EpisodeOfCareTrace row."""
    return EpisodeOfCareTrace(
        window_id=window_id,
        audit_input_encounters=focused.report.audit_input_encounters,
        audit_kept_by_guards=focused.report.audit_kept_by_guards,
        audit_kept_by_llm=focused.report.audit_kept_by_llm,
        audit_dropped_by_llm=[
            AuditFilterDrop(encounter_id=d.encounter_id, reason=d.reason)
            for d in focused.report.audit_dropped_by_llm
        ],
        audit_filter_failed=focused.report.audit_filter_failed,
        audit_filter_overflow=overflow,
        audit_parts=audit_parts,
        parts=list(parts),
    )


_SAFETY_NETTING_HINT_RX = re.compile(
    r"(?i)("
    r"cancer safety netting|y281b|safety net|safety-net|safety netted|"
    r"sn advice|if symptoms? worsen|if it gets worse|come back if|"
    r"return if|re-attend|reattend|will rebook if|"
    r"call 111|call 999|contact nhs 111|attend a&e if|seek urgent|"
    r"see your gp if|advice if worsens"
    r")"
)

_DISRUPTION_HINT_RX = re.compile(
    r"(?i)("
    r"no appointment letter|still no appointment|chasing referral|"
    r"referral not received|lost referral|gp to chase|"
    r"referral rejected|returned to gp|downgraded|asked for clarification|"
    r"re-referred|second referral|repeat 2ww|"
    r"did not attend|\bdna\b|no-show|"
    r"patient cancelled|patient rearranged|pt cancelled|pt rearranged|"
    r"cancelled by trust|clinic cancelled|hospital rescheduled|"
    r"appointment rescheduled|staff sickness|"
    r"awaiting result|result not back|no result yet|chasing histology|"
    r"awaiting biopsy|"
    r"unable to contact|no answer|no response after|"
    r"multiple attempts to contact|"
    r"mdt outcome unclear|no mdt plan"
    r")"
)

_ADMIN_NOISE_RX = re.compile(
    r"(?i)(note marked in error|diagnosis marked in error|"
    r"vt cancellation|pt vt cancelled|failed encounter)"
)


def _signal_hints(window_full: str) -> str:
    """Deterministic pre-scan for safety-netting / disruption candidates.

    The LLM is responsible for verifying each hint against the source
    encounter and rejecting admin noise. This step only ensures the
    signal does not drown in a long window.
    """
    sn_ids: list[str] = []
    dis_ids: list[str] = []
    for block in window_full.split("\n\n"):
        # First line is "[encounter_id] date"
        first = block.split("\n", 1)[0].strip()
        if not first.startswith("["):
            continue
        eid = first.split("]", 1)[0].lstrip("[")[:8]
        if not eid:
            continue
        # Strip well-known admin-noise lines so they do not generate a hint.
        cleaned = _ADMIN_NOISE_RX.sub(" ", block)
        if _SAFETY_NETTING_HINT_RX.search(cleaned):
            sn_ids.append(eid)
        if _DISRUPTION_HINT_RX.search(cleaned):
            dis_ids.append(eid)
    if not sn_ids and not dis_ids:
        return ""
    lines = ["HINTS (deterministic pre-scan; verify each before emitting):"]
    if sn_ids:
        lines.append(
            "  Possible safety_netting in encounters: " + ", ".join(sn_ids[:10])
        )
    if dis_ids:
        lines.append(
            "  Possible disruptions in encounters: " + ", ".join(dis_ids[:20])
        )
    return "\n".join(lines)


# -- Compiled subgraph + sync runner --------------------------------------


def build_episode_engine_subgraph() -> CompiledStateGraph:
    """Compile the episode-engine LangGraph subgraph."""
    g = StateGraph(EngineState)
    g.add_node("load_timeline", _node_load_timeline)
    g.add_node("segmenter", _node_segmenter)
    g.add_node("classifier", _node_classifier)
    g.add_node("audit_relevance_filter", _node_audit_relevance_filter)
    g.add_node("milestone_extractor", _node_milestone_extractor)
    g.add_node("reconciler", _node_reconciler)
    g.add_node("writer", _node_writer)

    g.add_edge(START, "load_timeline")
    g.add_edge("load_timeline", "segmenter")
    g.add_edge("segmenter", "classifier")
    g.add_edge("classifier", "audit_relevance_filter")
    g.add_edge("audit_relevance_filter", "milestone_extractor")
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
