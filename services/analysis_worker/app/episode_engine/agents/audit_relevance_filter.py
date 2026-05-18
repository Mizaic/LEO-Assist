"""Audit Relevance Filter (DI-LEO-AI-524).

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Two layers:

  1. ``apply_guards`` (deterministic, ``audit_guards.py``) marks every
     encounter that MUST be in the focused set regardless of any LLM
     opinion (cancer-coded, segmenter anchor, deterministic hint flag).

  2. The remaining "unguarded" encounters are batched in groups of up to
     ``BATCH_SIZE`` and sent to a Bedrock Haiku call with a forced
     ``submit_relevance`` tool. Each call returns one row per encounter:
     ``{encounter_id, keep, reason}``.

The focused set returned by ``run`` is the union of:

  * every guard-kept encounter (kept_by_guard=True), and
  * every encounter the LLM said keep=True (kept_by_llm=True), and
  * every encounter in a batch whose Haiku call failed or returned an
    unparseable response (kept_by_fallback=True).

A guard decision is FINAL: if the LLM later returns keep=False for an
encounter the guard already kept, the guard wins and the LLM verdict is
ignored. The audit trace records the guard reason for the encounter.

Chronological order is preserved (encounters are ordered by date then
encounter_id; ties broken by encounter_id).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from libs.llm_client.factory import LLMClient
from libs.prompts.episode_engine import audit_relevance_filter_v1
from services.analysis_worker.app.episode_engine.agents._common import (
    StageError,
    call_stage,
)
from services.analysis_worker.app.episode_engine.agents.audit_guards import (
    apply_guards,
)
from services.analysis_worker.app.episode_engine.schemas import (
    AuditFilterDrop,
    AuditFilterReport,
    FocusedEncounter,
    FocusedSet,
    StageTrace,
)

logger = logging.getLogger(__name__)


# Maximum encounters per Haiku batch. The prompt is built so each row is a
# short snippet, so 20 fits comfortably inside Haiku's input window.
BATCH_SIZE: int = 20

# Per-encounter snippet length sent to the Haiku triage. Long enough to
# carry the clinical hook; short enough that 20 rows do not blow the
# input window.
_BATCH_SNIPPET_CHARS: int = 360

# Cap on the {encounter_id, reason} drops we surface on the audit trace.
# More than this and the cohort dashboard becomes unreadable.
_DROPPED_SAMPLE_CAP: int = 10


# -- Pydantic response model --------------------------------------------


class _RelevanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    encounter_id: str
    keep: bool
    reason: str = ""


class _RelevanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[_RelevanceDecision] = Field(default_factory=list)


# -- Public entry point -------------------------------------------------


def run(
    *,
    llm: LLMClient,
    patient_id: str,
    window_id: str,
    suspected_site: str,
    encounters: list[Mapping[str, Any]],
    segmenter_anchors: Mapping[str, Iterable[str]] | None = None,
    cancer_coded_encounter_ids: Iterable[str] | None = None,
    hint_flagged_encounter_ids: Iterable[str] | None = None,
    batch_size: int = BATCH_SIZE,
) -> tuple[FocusedSet, list[StageTrace]]:
    """Filter ``encounters`` to the relevant subset for milestone extraction.

    Returns ``(focused_set, stage_traces)``. The focused set keeps original
    chronological order. ``stage_traces`` carries one StageTrace per Haiku
    batch call (zero if every encounter was already kept by a guard).
    """

    ordered = _order_chronologically(encounters)
    guard_reasons = apply_guards(
        encounters=ordered,
        segmenter_anchors=segmenter_anchors,
        cancer_coded_encounter_ids=cancer_coded_encounter_ids,
        hint_flagged_encounter_ids=hint_flagged_encounter_ids,
    )

    unguarded = [
        e for e in ordered if str(e.get("encounter_id") or "") not in guard_reasons
    ]

    decisions, traces, any_failed = _run_batches(
        llm=llm,
        patient_id=patient_id,
        window_id=window_id,
        suspected_site=suspected_site or "unknown",
        unguarded=unguarded,
        batch_size=max(1, int(batch_size)),
    )

    focused = _assemble_focused_set(
        ordered=ordered,
        guard_reasons=guard_reasons,
        decisions=decisions,
        any_failed=any_failed,
    )
    return focused, traces


# -- Helpers ------------------------------------------------------------


def _order_chronologically(
    encounters: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Sort encounters by (date, encounter_id). Stable, deterministic."""
    rows = [e for e in encounters if str((e or {}).get("encounter_id") or "")]
    return sorted(
        rows,
        key=lambda r: (str(r.get("date") or ""), str(r.get("encounter_id") or "")),
    )


def _run_batches(
    *,
    llm: LLMClient,
    patient_id: str,
    window_id: str,
    suspected_site: str,
    unguarded: list[Mapping[str, Any]],
    batch_size: int,
) -> tuple[
    dict[str, _RelevanceDecision],
    list[StageTrace],
    bool,
]:
    """Run the Haiku triage in fixed-size batches.

    Returns a per-encounter decision map, the per-batch StageTraces, and a
    flag indicating that at least one batch fell back to keep-all.
    """
    decisions: dict[str, _RelevanceDecision] = {}
    traces: list[StageTrace] = []
    any_failed = False
    if not unguarded:
        return decisions, traces, any_failed

    batches = _chunk(unguarded, batch_size)
    total = len(batches)
    for idx, batch in enumerate(batches, start=1):
        try:
            parsed, trace = _call_relevance(
                llm=llm,
                patient_id=patient_id,
                window_id=window_id,
                suspected_site=suspected_site,
                batch=batch,
                batch_index=idx,
                batch_total=total,
            )
            traces.append(trace)
        except StageError as exc:
            any_failed = True
            traces.append(_failed_trace(str(exc)))
            logger.warning(
                "audit_relevance_filter: batch %d/%d failed (size=%d); "
                "fail-open keep_all_unguarded for that batch -- %s",
                idx,
                total,
                len(batch),
                exc,
            )
            for enc in batch:
                eid = str(enc.get("encounter_id") or "")
                if eid:
                    decisions[eid] = _RelevanceDecision(
                        encounter_id=eid,
                        keep=True,
                        reason="LLM unavailable; kept by fail-open default",
                    )
            continue

        for d in parsed.decisions:
            if d.encounter_id:
                decisions[d.encounter_id] = d
    return decisions, traces, any_failed


def _call_relevance(
    *,
    llm: LLMClient,
    patient_id: str,
    window_id: str,
    suspected_site: str,
    batch: list[Mapping[str, Any]],
    batch_index: int,
    batch_total: int,
) -> tuple[_RelevanceResponse, StageTrace]:
    """One Haiku batch call; returns parsed response + trace."""
    encounters_block = _format_batch(batch)
    user = audit_relevance_filter_v1.USER_TEMPLATE.format(
        patient_id=patient_id,
        window_id=window_id,
        suspected_site=suspected_site,
        batch_index=batch_index,
        batch_total=batch_total,
        encounters_block=encounters_block,
    )
    return call_stage(
        stage="audit_relevance_filter",
        llm=llm,
        system=audit_relevance_filter_v1.SYSTEM,
        user=user,
        schema=audit_relevance_filter_v1.SCHEMA,
        tool_name=audit_relevance_filter_v1.TOOL_NAME,
        response_model=_RelevanceResponse,
        prompt_version=audit_relevance_filter_v1.VERSION,
        max_tokens=2048,
    )


def _format_batch(batch: list[Mapping[str, Any]]) -> str:
    """Render encounters as compact ``[id] date :: snippet`` rows."""
    lines: list[str] = []
    for enc in batch:
        eid = str(enc.get("encounter_id") or "")
        if not eid:
            continue
        date = str(enc.get("date") or "unknown")
        text = (
            enc.get("full_snippet")
            or enc.get("text")
            or enc.get("snippet")
            or ""
        )
        snippet = _normalise(str(text))[:_BATCH_SNIPPET_CHARS]
        lines.append(f"[{eid}] {date} :: {snippet}")
    return "\n".join(lines)


def _normalise(text: str) -> str:
    """Cheap whitespace normaliser for the per-row snippet."""
    return " ".join(text.split())


def _chunk(seq: list[Any], size: int) -> list[list[Any]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _assemble_focused_set(
    *,
    ordered: list[Mapping[str, Any]],
    guard_reasons: dict[str, str],
    decisions: dict[str, _RelevanceDecision],
    any_failed: bool,
) -> FocusedSet:
    """Combine guard + LLM decisions into the focused set + report."""
    focused: list[FocusedEncounter] = []
    dropped: list[AuditFilterDrop] = []
    kept_by_guard = 0
    kept_by_llm = 0
    for enc in ordered:
        eid = str(enc.get("encounter_id") or "")
        if not eid:
            continue
        date = enc.get("date") or None
        guard_reason = guard_reasons.get(eid)
        decision = decisions.get(eid)
        if guard_reason is not None:
            focused.append(
                FocusedEncounter(
                    encounter_id=eid,
                    encounter_date=date,
                    kept_by_guard=True,
                    guard_reason=guard_reason,
                    kept_by_llm=(decision.keep if decision is not None else None),
                    llm_reason=(decision.reason if decision is not None else None),
                )
            )
            kept_by_guard += 1
            continue
        if decision is None:
            continue
        if decision.keep:
            focused.append(
                FocusedEncounter(
                    encounter_id=eid,
                    encounter_date=date,
                    kept_by_guard=False,
                    kept_by_llm=True,
                    llm_reason=decision.reason,
                    kept_by_fallback=_is_fallback_decision(decision),
                )
            )
            kept_by_llm += 1
        else:
            if len(dropped) < _DROPPED_SAMPLE_CAP:
                dropped.append(AuditFilterDrop(encounter_id=eid, reason=decision.reason))

    report = AuditFilterReport(
        audit_input_encounters=len(ordered),
        audit_kept_by_guards=kept_by_guard,
        audit_kept_by_llm=kept_by_llm,
        audit_dropped_by_llm=dropped,
        audit_filter_failed=any_failed,
        audit_filter_overflow=False,
        audit_parts=1,
    )
    return FocusedSet(encounters=focused, report=report)


_FALLBACK_REASON_TOKEN = "LLM unavailable"


def _is_fallback_decision(decision: _RelevanceDecision) -> bool:
    return _FALLBACK_REASON_TOKEN in (decision.reason or "")


def _failed_trace(error: str) -> StageTrace:
    return StageTrace(
        stage="audit_relevance_filter",
        prompt_version=audit_relevance_filter_v1.VERSION,
        model_id="unknown",
        ok=False,
        error=error[:500],
    )
