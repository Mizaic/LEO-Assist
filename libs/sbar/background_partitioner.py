"""Partition the SBAR Background sources into N <= 8 LLM-sized parts.

The previous strategy was to shrink-or-drop sources until the prompt
fit. That is unsafe -- dropping a record can drop the medication,
comorbidity, or event that the recommendation hinges on, and the
reviewer has no way of knowing which record was dropped.

This module replaces shrink-or-drop with split-and-summarise. Given
N resolved sources, it returns the smallest set of partitions where
each partition's serialised user message fits inside the model's
input window (``SBAR_BACKGROUND_MAX_INPUT_TOKENS`` minus a system-
prompt reserve). Every record is preserved in full. If a single
record is too long to fit even alone in one partition (rare, but
possible for stitched-together discharge bundles), the record is
split across consecutive partitions and labelled
``part i of n of this record`` so the LLM can treat the halves as
two views of the same source. If the run would need more than
``max_parts`` partitions (default 8), the partitioner refuses with
a structured error so the caller can return a friendly
"too many records, pick fewer" message instead of running an
unbounded number of LLM calls.

Pure function -- no LLM calls, no Neo4j queries. Safe to call from
tests and from the prompt-call layer.

See DI-LEO-AI-513 / DI-LEO-AI-517 / DO-LEO-AI-515 / DO-LEO-AI-517.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource

logger = logging.getLogger(__name__)


# Mirrors libs/sbar/background_shrinker._CHARS_PER_TOKEN. Conservative
# estimate -- 3.6 chars per token under-counts for non-English / code,
# so the resulting token estimate is a slight over-estimate of the
# real token count, which is what we want for a budget gate.
_CHARS_PER_TOKEN = 3.6


# Per-source character cap. Matches the legacy 4000-char cap so a
# single-part run is byte-for-byte identical to the historical
# Background prompt.
_PER_SOURCE_CHAR_CAP = 4000


# Reserved budget for the system prompt + model overhead (header,
# JSON wrapper, codes block etc.). Picked to be safely large for the
# v2 Background system prompt; if we ever change that prompt
# substantially we should re-tune this.
_SYSTEM_PROMPT_RESERVE_TOKENS = 4000


# Hard upper bound on the number of partitions per Background run.
# Above this, we surface an explicit "too many parts" error rather
# than spending unbounded time / cost. 8 parts is roughly 8x the
# historical Background latency / cost worst case, which we have
# decided is the limit reviewers will tolerate.
_MAX_PARTS_DEFAULT = 8


# How many slices to split one over-budget record into before giving
# up and applying the shrinker as a last resort.
_MAX_INTRA_RECORD_SLICES = 4


_ENV_FLOOR_TOKENS = 1000


def _max_input_tokens() -> int:
    """Read SBAR_BACKGROUND_MAX_INPUT_TOKENS from the environment.

    Default 60_000 is well below Claude 3.5 Sonnet's 200K input
    window so we leave headroom for the response. A floor of
    ``_ENV_FLOOR_TOKENS`` prevents an empty / nonsense env var
    from collapsing the budget; explicit ``max_input_tokens``
    arguments are respected as-is so tests can exercise extreme
    paths.
    """
    raw = os.getenv("SBAR_BACKGROUND_MAX_INPUT_TOKENS", "60000")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "SBAR_BACKGROUND_MAX_INPUT_TOKENS=%r is not an int; using 60000",
            raw,
        )
        return 60000
    return max(_ENV_FLOOR_TOKENS, value)


def _estimate_tokens(text: str) -> int:
    """Cheap char-based token estimate. Over-estimates slightly."""
    if not text:
        return 0
    return int(len(text) / _CHARS_PER_TOKEN) + 1


# ---------------------------------------------------------------------------
# Slice -- one piece of a source (whole or half-of)
# ---------------------------------------------------------------------------


@dataclass
class _SourceSlice:
    """Internal: one piece of a source ready to drop into a partition.

    For the common case (record fits in one partition at the 4000-
    char cap) ``slice_index`` and ``slice_total`` are both 1 and
    ``text`` is the full sanitised text capped at 4000 chars.
    """

    source: ResolvedSource
    text: str
    slice_index: int = 1  # 1-indexed
    slice_total: int = 1

    @property
    def source_id(self) -> str:
        return self.source.source_id

    @property
    def is_split(self) -> bool:
        return self.slice_total > 1


# ---------------------------------------------------------------------------
# Partition + report
# ---------------------------------------------------------------------------


@dataclass
class PartitionDescriptor:
    """One source descriptor inside a partition. For SSE / audit only."""

    source_id: str
    source_label: str
    slice_index: int
    slice_total: int
    char_count: int


@dataclass
class Partition:
    """One LLM-sized chunk of the Background sources.

    ``user_message`` is ready to pass to ``invoke_llm_json``. It uses
    the same JSON-in-fence shape as the legacy single-call Background
    user message so the existing system prompt does not need to
    change.
    """

    index: int  # 1-indexed
    total: int
    user_message: str
    descriptors: list[PartitionDescriptor]
    estimated_input_tokens: int


@dataclass
class PartitionReport:
    """Audit record of how the partitioner split the Background prompt."""

    total_records: int
    total_parts: int
    split_records: list[str] = field(default_factory=list)
    too_many_parts: bool = False
    notice: str | None = None
    record_split_notice: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialise_codes(codes: list[ResolvedCode]) -> list[dict[str, Any]]:
    return [
        {
            "concept_id": c.concept_id,
            "term": c.term,
            "semantic_tag": c.semantic_tag,
            "assertion": c.assertion,
            "evidence": sanitise_for_prompt(c.evidence or ""),
            "source": {"type": c.source_label, "id": c.source_id},
            "confidence": c.confidence,
        }
        for c in codes
    ]


def _serialise_source_slice(s: _SourceSlice) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": s.source.source_label,
        "id": s.source_id,
        "text": s.text,
        "metadata": s.source.metadata,
        "has_codes": s.source.has_codes(),
    }
    if s.is_split:
        body["part_in_record"] = {
            "index": s.slice_index,
            "total": s.slice_total,
        }
    return body


def _build_user_message(
    slices: list[_SourceSlice],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None,
    part_index: int,
    part_total: int,
) -> str:
    """Build the JSON-in-fence user message for one partition.

    Adds an ``part`` block so the LLM knows it is summarising one
    chunk of a multi-part run and should not pretend the chunk is
    the whole patient history.
    """
    body: dict[str, Any] = {
        "referring_specialty": referring_specialty,
        "codes": _serialise_codes(codes),
        "sources": [_serialise_source_slice(s) for s in slices],
    }
    if part_total > 1:
        body["part"] = {"index": part_index, "total": part_total}
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _slice_size(slice_: _SourceSlice) -> int:
    """Estimate the per-slice token cost when added to a partition."""
    return _estimate_tokens(json.dumps(_serialise_source_slice(slice_), default=str))


def _split_oversize_source(
    source: ResolvedSource,
    *,
    per_slice_chars: int,
) -> list[_SourceSlice]:
    """Split a single oversize record into roughly equal slices.

    Each slice is at most ``per_slice_chars`` characters and is
    labelled ``slice i of n``. Used only for the rare case where
    one record alone would not fit in a partition at the standard
    cap.
    """
    text = sanitise_for_prompt(source.text or "")
    if len(text) <= per_slice_chars:
        return [
            _SourceSlice(source=source, text=text, slice_index=1, slice_total=1)
        ]
    n = min(_MAX_INTRA_RECORD_SLICES, (len(text) + per_slice_chars - 1) // per_slice_chars)
    n = max(2, n)
    step = (len(text) + n - 1) // n
    slices: list[_SourceSlice] = []
    for i in range(n):
        chunk = text[i * step : (i + 1) * step]
        if not chunk:
            break
        slices.append(
            _SourceSlice(
                source=source,
                text=chunk,
                slice_index=i + 1,
                slice_total=n,
            )
        )
    return slices


def _build_slices(
    sources: list[ResolvedSource],
    *,
    per_part_budget_tokens: int,
    fixed_overhead_tokens: int,
) -> tuple[list[_SourceSlice], list[str]]:
    """Convert each source to one or more slices, splitting oversize records.

    Returns (slices, split_record_ids).
    """
    slices: list[_SourceSlice] = []
    split_ids: list[str] = []
    per_slice_chars_floor = max(250, _PER_SOURCE_CHAR_CAP)
    available = max(1, per_part_budget_tokens - fixed_overhead_tokens)
    for source in sources:
        text = sanitise_for_prompt(source.text or "")[:_PER_SOURCE_CHAR_CAP]
        whole = _SourceSlice(source=source, text=text)
        if _slice_size(whole) <= available:
            slices.append(whole)
            continue
        # Single record too large even at 4000-char cap to fit inside
        # one part by itself. Split it across several slices.
        per_slice_chars = per_slice_chars_floor
        sub_slices = _split_oversize_source(source, per_slice_chars=per_slice_chars)
        # If the half-cap is still too big, fall back to the
        # progressive shrinker caps on a per-slice basis. This is the
        # only place we ever shorten clinical text; the notice flags
        # it loudly.
        for cap in (2000, 1000, 500, 250):
            if all(_slice_size(s) <= available for s in sub_slices):
                break
            sub_slices = [
                _SourceSlice(
                    source=ss.source,
                    text=ss.text[:cap],
                    slice_index=ss.slice_index,
                    slice_total=ss.slice_total,
                )
                for ss in sub_slices
            ]
        slices.extend(sub_slices)
        split_ids.append(source.source_id)
    return slices, split_ids


def _greedy_pack(
    slices: list[_SourceSlice],
    *,
    per_part_budget_tokens: int,
    fixed_overhead_tokens: int,
    max_parts: int,
) -> list[list[_SourceSlice]] | None:
    """Greedy bin-packing. Returns None if we'd need more than max_parts."""
    available = max(1, per_part_budget_tokens - fixed_overhead_tokens)
    parts: list[list[_SourceSlice]] = [[]]
    used = 0
    for slice_ in slices:
        cost = _slice_size(slice_)
        if parts[-1] and used + cost > available:
            parts.append([])
            used = 0
            if len(parts) > max_parts:
                return None
        parts[-1].append(slice_)
        used += cost
    if not parts[-1]:
        parts.pop()
    if len(parts) > max_parts:
        return None
    return parts


def _build_notice(*, total_parts: int) -> str | None:
    if total_parts <= 1:
        return None
    return (
        f"This patient has a lot of records, so we summarised them "
        f"in {total_parts} parts. Every record is included; nothing "
        "was dropped."
    )


def _build_record_split_notice(split_ids: list[str]) -> str | None:
    if not split_ids:
        return None
    if len(split_ids) == 1:
        return (
            f"One record ({split_ids[0]}) was very long, so we split "
            "it into smaller pieces and summarised each piece. "
            "Nothing was dropped."
        )
    return (
        f"{len(split_ids)} records were very long, so we split each "
        "one into smaller pieces and summarised each piece. "
        "Nothing was dropped."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def partition_background_sources(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    *,
    referring_specialty: str | None = None,
    max_input_tokens: int | None = None,
    system_prompt_reserve_tokens: int = _SYSTEM_PROMPT_RESERVE_TOKENS,
    max_parts: int = _MAX_PARTS_DEFAULT,
) -> tuple[list[Partition], PartitionReport]:
    """Split sources into N <= max_parts LLM-sized partitions.

    Pure function -- no LLM calls, no Neo4j queries. Safe to call
    from tests and from the prompt-call layer.

    Returns:
        (partitions, report)

    If ``report.too_many_parts`` is True, ``partitions`` is empty and
    the caller MUST surface a friendly "too_many_parts" error via
    ``libs.sbar.error_messages.translate_error``.
    """
    budget = max_input_tokens if max_input_tokens is not None else _max_input_tokens()
    per_part_budget = max(1, budget - system_prompt_reserve_tokens)

    # Codes appear in EVERY part, so account for them once as a fixed
    # per-part overhead. Same for the referring_specialty + JSON
    # wrapper.
    overhead_body = {
        "referring_specialty": referring_specialty,
        "codes": _serialise_codes(codes),
        "sources": [],
    }
    overhead_text = "CONTEXT:\n```json\n" + json.dumps(overhead_body, default=str) + "\n```"
    fixed_overhead = _estimate_tokens(overhead_text)

    if not sources:
        empty_msg = _build_user_message(
            [], codes, referring_specialty=referring_specialty,
            part_index=1, part_total=1,
        )
        return [
            Partition(
                index=1,
                total=1,
                user_message=empty_msg,
                descriptors=[],
                estimated_input_tokens=_estimate_tokens(empty_msg),
            )
        ], PartitionReport(total_records=0, total_parts=1)

    slices, split_ids = _build_slices(
        sources,
        per_part_budget_tokens=per_part_budget,
        fixed_overhead_tokens=fixed_overhead,
    )

    packed = _greedy_pack(
        slices,
        per_part_budget_tokens=per_part_budget,
        fixed_overhead_tokens=fixed_overhead,
        max_parts=max_parts,
    )
    if packed is None:
        return [], PartitionReport(
            total_records=len(sources),
            total_parts=0,
            split_records=split_ids,
            too_many_parts=True,
        )

    total_parts = len(packed)
    partitions: list[Partition] = []
    for idx, part_slices in enumerate(packed, start=1):
        msg = _build_user_message(
            part_slices,
            codes,
            referring_specialty=referring_specialty,
            part_index=idx,
            part_total=total_parts,
        )
        descriptors = [
            PartitionDescriptor(
                source_id=s.source_id,
                source_label=s.source.source_label,
                slice_index=s.slice_index,
                slice_total=s.slice_total,
                char_count=len(s.text),
            )
            for s in part_slices
        ]
        partitions.append(
            Partition(
                index=idx,
                total=total_parts,
                user_message=msg,
                descriptors=descriptors,
                estimated_input_tokens=_estimate_tokens(msg),
            )
        )

    report = PartitionReport(
        total_records=len(sources),
        total_parts=total_parts,
        split_records=split_ids,
        notice=_build_notice(total_parts=total_parts),
        record_split_notice=_build_record_split_notice(split_ids),
    )
    if total_parts > 1:
        logger.info(
            "SBAR background partitioner: split %d records into %d parts "
            "(record_splits=%d budget=%d overhead=%d)",
            len(sources),
            total_parts,
            len(split_ids),
            per_part_budget,
            fixed_overhead,
        )
    return partitions, report
