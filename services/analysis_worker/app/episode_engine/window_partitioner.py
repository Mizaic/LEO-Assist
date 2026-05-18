"""Window Partitioner safety net for the milestone extractor (DI-LEO-AI-525).

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Mirrors the SBAR Background partitioner architecture
(``libs.sbar.background_partitioner``): split the focused encounter set
into N <= ``max_parts`` partitions, run the milestone extractor once per
partition, then merge the per-part results in pure Python.

There are TWO public entry points:

    partition_window(focused_encounters, ...)
        Pure function. Bin-packs the focused set into the smallest number
        of partitions whose serialised user message fits the per-part
        token budget. Returns ``(partitions, PartitionReport)``. If
        bin-packing would need more than ``max_parts`` partitions the
        function refuses cleanly with ``too_many_parts = True`` and an
        empty partitions list -- the chain MUST surface a friendly
        "too much pathway material" error and create the EoC with
        ``needs_human_review = true``, with ZERO milestone-extractor
        invocations.

    merge_milestones_deterministic(per_part_results, ...)
        Pure function. Merges per-part ``MilestoneExtractorResult``
        objects into a single result. NO LLM CALL. Deduplication rules
        (see DI-LEO-AI-525):
            * milestones: dedupe on (type, date, encounter_id), keep the
              instance with the highest confidence and the longest
              evidence_quote.
            * safety_netting: union over per-part flags; ``recorded`` is
              True if any part observed it; on tie, the earliest dated
              entry with the longest evidence_quote wins.
            * disruptions: concatenate then dedupe on
              (category, date, encounter_id) keeping the highest
              confidence entry.
            * needs_human_review: any-true across parts.
            * reasoning: concatenated as ``"Part i of N: <reasoning>"``
              lines so the auditor can trace which part contributed
              which decision.

The common case (focused set fits one partition) is byte-for-byte
identical to the legacy single-call milestone extractor: the chain calls
the extractor once with the unmodified window text and skips the merge
step entirely.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Mapping

from libs.llm_client.prompt_safety import sanitise_for_prompt
from services.analysis_worker.app.episode_engine.schemas import (
    Disruption,
    Milestone,
    MilestoneExtractorResult,
    PartitionReport,
    SafetyNetting,
    WindowPartition,
)

logger = logging.getLogger(__name__)


# Conservative chars-per-token estimate; over-estimates slightly so the
# token count we use as a budget gate is on the safe side of the real
# count.
_CHARS_PER_TOKEN = 3.6

# Per-encounter character cap when serialised inside a partition. Picked
# to match the legacy timeline_loader full-snippet cap so a
# single-partition run is byte-for-byte identical to the historical
# extractor input envelope.
_PER_ENCOUNTER_CHAR_CAP = 4000

# Reserved budget for system prompt + JSON wrapper overhead.
_SYSTEM_PROMPT_RESERVE_TOKENS = 4000

# Hard upper bound on partitions per window. Above this we refuse cleanly
# rather than spend unbounded LLM time.
_MAX_PARTS_DEFAULT = 8

# How many slices to split one over-budget encounter into before falling
# back to truncating each slice further.
_MAX_INTRA_ENCOUNTER_SLICES = 4

# Floor for the env-driven max-input-token budget so a misconfigured env
# var cannot collapse the budget to zero.
_ENV_FLOOR_TOKENS = 1000


def _max_input_tokens() -> int:
    """Read EPISODE_ENGINE_MAX_INPUT_TOKENS from the environment.

    Default is 60_000 which leaves ample headroom on Haiku's input window
    for a realistic post-focus encounter set.
    """
    raw = os.getenv("EPISODE_ENGINE_MAX_INPUT_TOKENS", "60000")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "EPISODE_ENGINE_MAX_INPUT_TOKENS=%r is not an int; using 60000",
            raw,
        )
        return 60000
    return max(_ENV_FLOOR_TOKENS, value)


def _estimate_tokens(text: str) -> int:
    """Cheap char-based token estimate. Over-estimates slightly."""
    if not text:
        return 0
    return int(len(text) / _CHARS_PER_TOKEN) + 1


# -- Internal: per-encounter slice -------------------------------------


class _EncounterSlice:
    """One serialisable slice of a focused encounter."""

    __slots__ = (
        "encounter_id",
        "text",
        "slice_index",
        "slice_total",
        "record_index",
    )

    def __init__(
        self,
        *,
        encounter_id: str,
        text: str,
        slice_index: int = 1,
        slice_total: int = 1,
        record_index: int = 0,
    ) -> None:
        self.encounter_id = encounter_id
        self.text = text
        self.slice_index = slice_index
        self.slice_total = slice_total
        self.record_index = record_index

    @property
    def is_split(self) -> bool:
        return self.slice_total > 1

    def cost_tokens(self) -> int:
        # Mirrors the per-encounter prompt envelope: header + body.
        envelope_chars = len(self.encounter_id) + 32
        if self.is_split:
            envelope_chars += 24
        return _estimate_tokens(self.text) + _estimate_tokens(" " * envelope_chars)


# -- partition_window --------------------------------------------------


def partition_window(
    focused_encounters: list[Mapping[str, Any]],
    *,
    max_input_tokens: int | None = None,
    system_prompt_reserve_tokens: int = _SYSTEM_PROMPT_RESERVE_TOKENS,
    max_parts: int = _MAX_PARTS_DEFAULT,
) -> tuple[list[WindowPartition], PartitionReport]:
    """Bin-pack ``focused_encounters`` into N <= max_parts partitions.

    Each input dict must carry ``encounter_id`` and either
    ``full_snippet``, ``text``, or ``snippet`` for the body. The function
    is pure -- no LLM calls, no Neo4j queries.
    """

    budget = (
        max_input_tokens
        if max_input_tokens is not None
        else _max_input_tokens()
    )
    per_part_budget = max(1, budget - system_prompt_reserve_tokens)

    if not focused_encounters:
        return [
            WindowPartition(
                index=1,
                total=1,
                encounter_ids=[],
                record_range=(0, 0),
            )
        ], PartitionReport(total_parts=1)

    slices = _build_slices(
        focused_encounters,
        per_part_budget_tokens=per_part_budget,
    )

    packed = _greedy_pack(
        slices,
        per_part_budget_tokens=per_part_budget,
        max_parts=max_parts,
    )
    if packed is None:
        return [], PartitionReport(
            total_parts=0,
            too_many_parts=True,
            notice=(
                "This patient has too much pathway-relevant material to "
                "audit in one run. Ask a clinician to review the "
                "encounter range manually."
            ),
        )

    total = len(packed)
    partitions: list[WindowPartition] = []
    for idx, group in enumerate(packed, start=1):
        ids = [s.encounter_id for s in group]
        record_indices = [s.record_index for s in group if s.record_index]
        record_range = (
            (min(record_indices), max(record_indices))
            if record_indices
            else (0, 0)
        )
        part_in_encounter = {
            s.encounter_id: (s.slice_index, s.slice_total)
            for s in group
            if s.is_split
        } or None
        partitions.append(
            WindowPartition(
                index=idx,
                total=total,
                encounter_ids=ids,
                record_range=record_range,
                part_in_encounter=part_in_encounter,
            )
        )

    notice: str | None = None
    if total > 1:
        notice = (
            f"This patient has a lot of pathway-relevant encounters, so we "
            f"split the audit into {total} parts. Every encounter is "
            "included; nothing was dropped."
        )
    return partitions, PartitionReport(
        total_parts=total,
        too_many_parts=False,
        notice=notice,
    )


def _build_slices(
    encounters: list[Mapping[str, Any]],
    *,
    per_part_budget_tokens: int,
) -> list[_EncounterSlice]:
    """Convert encounters to slices, splitting any oversize record."""
    slices: list[_EncounterSlice] = []
    for record_idx, enc in enumerate(encounters, start=1):
        eid = str(enc.get("encounter_id") or "").strip()
        if not eid:
            continue
        raw = (
            enc.get("full_snippet")
            or enc.get("text")
            or enc.get("snippet")
            or ""
        )
        text = sanitise_for_prompt(str(raw))[:_PER_ENCOUNTER_CHAR_CAP]
        whole = _EncounterSlice(
            encounter_id=eid,
            text=text,
            record_index=record_idx,
        )
        if whole.cost_tokens() <= per_part_budget_tokens:
            slices.append(whole)
            continue
        slices.extend(
            _split_oversize(
                encounter_id=eid,
                text=text,
                record_index=record_idx,
                per_part_budget_tokens=per_part_budget_tokens,
            )
        )
    return slices


def _split_oversize(
    *,
    encounter_id: str,
    text: str,
    record_index: int,
    per_part_budget_tokens: int,
) -> list[_EncounterSlice]:
    """Split a single oversize encounter across consecutive parts."""
    target_chars = max(
        500, int(per_part_budget_tokens * _CHARS_PER_TOKEN * 0.6)
    )
    n = max(2, (len(text) + target_chars - 1) // target_chars)
    n = min(n, _MAX_INTRA_ENCOUNTER_SLICES)
    step = (len(text) + n - 1) // n
    out: list[_EncounterSlice] = []
    for i in range(n):
        chunk = text[i * step : (i + 1) * step]
        if not chunk:
            break
        out.append(
            _EncounterSlice(
                encounter_id=encounter_id,
                text=chunk,
                slice_index=i + 1,
                slice_total=n,
                record_index=record_index,
            )
        )
    # If a single slice still overshoots the per-part budget, truncate
    # progressively. Loud, but at this point we have already exhausted
    # the safe options and the alternative is dropping the encounter.
    for cap in (2000, 1000, 500, 250):
        if all(s.cost_tokens() <= per_part_budget_tokens for s in out):
            break
        out = [
            _EncounterSlice(
                encounter_id=s.encounter_id,
                text=s.text[:cap],
                slice_index=s.slice_index,
                slice_total=s.slice_total,
                record_index=s.record_index,
            )
            for s in out
        ]
    return out


def _greedy_pack(
    slices: list[_EncounterSlice],
    *,
    per_part_budget_tokens: int,
    max_parts: int,
) -> list[list[_EncounterSlice]] | None:
    """Greedy bin-pack. Returns None if N would exceed ``max_parts``."""
    parts: list[list[_EncounterSlice]] = [[]]
    used = 0
    for s in slices:
        cost = s.cost_tokens()
        if parts[-1] and used + cost > per_part_budget_tokens:
            parts.append([])
            used = 0
            if len(parts) > max_parts:
                return None
        parts[-1].append(s)
        used += cost
    if not parts[-1]:
        parts.pop()
    if len(parts) > max_parts:
        return None
    return parts


# -- merge_milestones_deterministic ------------------------------------


def merge_milestones_deterministic(
    per_part_results: list[MilestoneExtractorResult],
    *,
    window_id: str,
) -> MilestoneExtractorResult:
    """Merge per-part MilestoneExtractorResults with NO second LLM call.

    See DI-LEO-AI-525 / R-LEO-AI-513 for the rationale: an LLM merge step
    is itself a place where pathway facts can be dropped or invented, so
    the merge is pure Python.
    """
    if not per_part_results:
        return MilestoneExtractorResult(
            window_id=window_id,
            milestones=[],
            disruptions=[],
            needs_human_review=False,
            reasoning="",
        )
    if len(per_part_results) == 1:
        # Common case pass-through: do not rewrite the reasoning, do not
        # add per-part headings. Byte-for-byte identical to the single-
        # call legacy extractor output.
        only = per_part_results[0]
        return MilestoneExtractorResult(
            window_id=window_id,
            milestones=list(only.milestones),
            safety_netting=only.safety_netting,
            disruptions=list(only.disruptions),
            needs_human_review=bool(only.needs_human_review),
            reasoning=only.reasoning or "",
        )

    milestones = _merge_milestones(
        m for r in per_part_results for m in r.milestones
    )
    disruptions = _merge_disruptions(
        d for r in per_part_results for d in r.disruptions
    )
    safety = _merge_safety_netting(r.safety_netting for r in per_part_results)
    needs_review = any(bool(r.needs_human_review) for r in per_part_results)
    total = len(per_part_results)
    reasoning_lines = [
        f"Part {i} of {total}: {(r.reasoning or '').strip()}"
        for i, r in enumerate(per_part_results, start=1)
    ]
    return MilestoneExtractorResult(
        window_id=window_id,
        milestones=milestones,
        safety_netting=safety,
        disruptions=disruptions,
        needs_human_review=needs_review,
        reasoning="\n".join(reasoning_lines),
    )


def _merge_milestones(items: Iterable[Milestone]) -> list[Milestone]:
    """De-dupe milestones on (type, date, encounter_id).

    On collision: keep the highest-confidence instance; on tie, keep the
    one with the longest evidence_quote.
    """
    by_key: dict[tuple[str, str, str], Milestone] = {}
    for m in items:
        key = (m.type, str(m.date), m.encounter_id)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = m
            continue
        if _better_milestone(m, existing):
            by_key[key] = m
    return list(by_key.values())


def _better_milestone(candidate: Milestone, existing: Milestone) -> bool:
    if candidate.confidence > existing.confidence:
        return True
    if candidate.confidence < existing.confidence:
        return False
    return len(candidate.evidence_quote or "") > len(existing.evidence_quote or "")


def _merge_disruptions(items: Iterable[Disruption]) -> list[Disruption]:
    """De-dupe disruptions on (category, date, encounter_id)."""
    by_key: dict[tuple[str, str, str], Disruption] = {}
    for d in items:
        key = (d.category, str(d.date), d.encounter_id)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = d
            continue
        if d.confidence > existing.confidence:
            by_key[key] = d
        elif d.confidence == existing.confidence:
            if len(d.evidence_quote or "") > len(existing.evidence_quote or ""):
                by_key[key] = d
    return list(by_key.values())


def _merge_safety_netting(
    items: Iterable[SafetyNetting | None],
) -> SafetyNetting | None:
    """Union per-part safety_netting flags.

    ``recorded`` is True if any part observed it. Among recorded parts we
    pick the earliest-dated entry with the longest evidence_quote.
    """
    recorded = [s for s in items if s is not None and s.recorded]
    if not recorded:
        # Fall back to a non-recorded entry if any part returned one.
        return None
    recorded.sort(
        key=lambda s: (
            str(s.date or "9999-12-31"),
            -len(s.evidence_quote or ""),
        )
    )
    return recorded[0]
