"""Policy-driven extraction window planner and merge (C3.1-C3.3).

Atlas trace:
  DO: DO-CA3BBC37, DO-292D7D75
  DI: DI-090D4939, DI-29BF950F, DI-33376FBB, DI-452DA083, DI-8788B246,
      DI-8A2F4DAB, DI-9EE8D65E, DI-AB1C442D, DI-CB01B8A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-292D7D75")
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Headroom for prompt labels + dynamic few-shot block inside the user message.
DEFAULT_PROMPT_OVERHEAD_TOKENS = 800
TRUNCATION_MARKER = "\n...[truncated]..."

# Floor on a slice of an oversized chunk. Without it, a small window budget
# against a large prompt overhead yields a negative allowance and would cut
# the chunk into thousands of one-character windows.
MIN_CHUNK_SLICE_CHARS = 400


@dataclass(frozen=True)
class ChunkRef:
    chunk_id: str
    text: str = ""


@dataclass(frozen=True)
class ExtractionWindow:
    index: int
    chunk_ids: tuple[str, ...]
    input_hash: str
    truncated: bool = False
    # ``[start, end)`` within the single chunk this window covers, set only
    # when an oversized chunk had to be split across several windows.
    text_slice: tuple[int, int] | None = None


def window_chunk_text(window: ExtractionWindow, chunk_id: str, text: str) -> str:
    """Return the part of ``text`` this window covers.

    Safe to call for every chunk of every window: a window that was not
    split returns the chunk whole.
    """
    text_slice = getattr(window, "text_slice", None)
    if text_slice is None or window.chunk_ids != (chunk_id,):
        return text
    start, end = text_slice
    return text[start:end]


def split_text_on_line_boundaries(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Split ``text`` into ``[start, end)`` ranges covering all of it.

    Breaks are taken at the last newline inside the budget, because a
    window edge landing mid-line can sever a lab result from its value. A
    single line longer than the budget is cut at character level, since
    losing the line entirely is worse than splitting it.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    ranges: list[tuple[int, int]] = []
    pos = 0
    total = len(text)
    while pos < total:
        end = min(total, pos + max_chars)
        if end < total:
            cut = text.rfind("\n", pos + 1, end)
            if cut > pos:
                end = cut + 1
        ranges.append((pos, end))
        pos = end
    return ranges


@dataclass
class WindowUsage:
    window_index: int
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    attempt: int = 1


@dataclass
class WindowMergeResult:
    entities: list[dict[str, Any]] = field(default_factory=list)
    window_usages: list[WindowUsage] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    """Cheap chars/4 estimator for packing (not tokenizer-accurate)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _window_payload_tokens(
    chunk_ids: list[str],
    texts: dict[str, str],
    *,
    overhead_tokens: int,
    estimate_fn: Callable[[str], int],
) -> int:
    context = "\n\n".join(texts.get(cid, "") for cid in chunk_ids)
    sentence_block = "\n".join(f"[{cid}] {texts.get(cid, '')}" for cid in chunk_ids)
    return (
        estimate_fn(context)
        + estimate_fn(sentence_block)
        + max(0, int(overhead_tokens))
    )


def _make_window(
    index: int,
    chunk_ids: tuple[str, ...],
    texts: dict[str, str],
    *,
    truncated: bool = False,
    text_slice: tuple[int, int] | None = None,
) -> ExtractionWindow:
    payload = "|".join(f"{cid}:{texts.get(cid, '')}" for cid in chunk_ids)
    if text_slice is not None:
        payload = f"{payload}|slice:{text_slice[0]}-{text_slice[1]}"
    return ExtractionWindow(
        index=index,
        chunk_ids=chunk_ids,
        input_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        truncated=truncated,
        text_slice=text_slice,
    )


def _chunk_slice_budget_chars(
    chunk_id: str, *, max_window_input_tokens: int, overhead_tokens: int
) -> int:
    """Characters of one chunk that fit inside a single window.

    ``_window_payload_tokens`` counts the chunk text twice, once as context
    and once in the labelled sentence block, so the character allowance is
    half the tokens left after prompt overhead.
    """
    label_tokens = estimate_tokens(f"[{chunk_id}] ")
    available = max_window_input_tokens - max(0, int(overhead_tokens)) - label_tokens
    return max(MIN_CHUNK_SLICE_CHARS, (available * 4) // 2)


def _oversized_chunk_windows(
    first_index: int,
    chunk_id: str,
    texts: dict[str, str],
    *,
    max_window_input_tokens: int,
    overhead_tokens: int,
) -> list[ExtractionWindow]:
    """Spread one oversized chunk across windows instead of cutting it.

    HCCP does not guarantee a chunk fits a window. Emitting the chunk alone
    and letting the caller trim it to the budget silently drops the bottom
    of the chunk, which on production referrals is where the blood panel
    and examination narrative sit. Splitting costs extra model calls.
    """
    text = texts.get(chunk_id, "")
    budget = _chunk_slice_budget_chars(
        chunk_id,
        max_window_input_tokens=max_window_input_tokens,
        overhead_tokens=overhead_tokens,
    )
    return [
        _make_window(first_index + offset, (chunk_id,), texts, text_slice=bounds)
        for offset, bounds in enumerate(split_text_on_line_boundaries(text, budget))
    ]


def plan_extraction_windows(
    chunks: list[ChunkRef],
    *,
    window_size: int = 10,
    window_overlap: int = 1,
) -> list[ExtractionWindow]:
    """Plan ordered windows from pinned policy defaults (chunk-count mode)."""
    if window_size < 1:
        raise ValueError("window_size must be >= 1")
    if window_overlap < 0 or window_overlap >= window_size:
        raise ValueError("window_overlap must be >= 0 and < window_size")
    if not chunks:
        return []

    ids = [c.chunk_id for c in chunks]
    texts = {c.chunk_id: c.text for c in chunks}
    step = max(1, window_size - window_overlap)
    windows: list[ExtractionWindow] = []
    start = 0
    idx = 1
    while start < len(ids):
        window_ids = tuple(ids[start : start + window_size])  # noqa: E203
        windows.append(_make_window(idx, window_ids, texts))
        idx += 1
        if start + window_size >= len(ids):
            break
        start += step
    return windows


def plan_extraction_windows_by_tokens(
    chunks: list[ChunkRef],
    *,
    max_window_input_tokens: int,
    window_overlap_chunks: int = 1,
    max_chunks_per_window: int = 10,
    overhead_tokens: int = DEFAULT_PROMPT_OVERHEAD_TOKENS,
    estimate_fn: Callable[[str], int] | None = None,
) -> list[ExtractionWindow]:
    """Pack chunks by estimated prompt tokens; never drop an oversized chunk."""
    if max_window_input_tokens < 1:
        raise ValueError("max_window_input_tokens must be >= 1")
    if max_chunks_per_window < 1:
        raise ValueError("max_chunks_per_window must be >= 1")
    if window_overlap_chunks < 0 or window_overlap_chunks >= max_chunks_per_window:
        raise ValueError(
            "window_overlap_chunks must be >= 0 and < max_chunks_per_window"
        )
    if not chunks:
        return []

    estimate = estimate_fn or estimate_tokens
    texts = {c.chunk_id: c.text for c in chunks}
    ids = [c.chunk_id for c in chunks]
    windows: list[ExtractionWindow] = []
    idx = 1
    start = 0
    while start < len(ids):
        head = ids[start]
        if (
            _window_payload_tokens(
                [head],
                texts,
                overhead_tokens=overhead_tokens,
                estimate_fn=estimate,
            )
            > max_window_input_tokens
        ):
            sliced = _oversized_chunk_windows(
                idx,
                head,
                texts,
                max_window_input_tokens=max_window_input_tokens,
                overhead_tokens=overhead_tokens,
            )
            windows.extend(sliced)
            idx += len(sliced)
            start += 1
            continue
        packed: list[str] = []
        for offset in range(max_chunks_per_window):
            if start + offset >= len(ids):
                break
            candidate = ids[start + offset]
            trial = packed + [candidate]
            tokens = _window_payload_tokens(
                trial,
                texts,
                overhead_tokens=overhead_tokens,
                estimate_fn=estimate,
            )
            if tokens > max_window_input_tokens:
                break
            packed = trial
        if not packed:
            break
        windows.append(_make_window(idx, tuple(packed), texts))
        idx += 1
        if start + len(packed) >= len(ids):
            break
        step = max(1, len(packed) - window_overlap_chunks)
        start += step
    return windows


def truncate_text_to_token_budget(text: str, max_tokens: int) -> str:
    """Soft-truncate text to an approximate token budget."""
    if max_tokens < 1 or estimate_tokens(text) <= max_tokens:
        return text
    # Leave room for the truncation marker.
    marker_tokens = estimate_tokens(TRUNCATION_MARKER)
    budget_chars = max(0, (max_tokens - marker_tokens) * 4)
    if budget_chars <= 0:
        return TRUNCATION_MARKER.strip()
    return text[:budget_chars] + TRUNCATION_MARKER


def merge_window_entities(
    window_outputs: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge entities across windows by concept, chunk provenance and assertion."""
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for entities in window_outputs:
        for entity in entities:
            concept = str(entity.get("concept_id") or entity.get("text") or "")
            chunk_id = str(entity.get("chunk_id") or "")
            sentence_id = str(entity.get("sentence_id") or "")
            assertion = str(entity.get("assertion") or "present").lower()
            key = (concept, chunk_id, sentence_id, assertion)
            if key not in merged:
                merged[key] = dict(entity)
    return list(merged.values())


def aggregate_window_usage(usages: list[WindowUsage]) -> dict[str, Any]:
    """Sum tokens, cache, latency and cost without losing per-window detail."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "latency_ms": 0,
        "cost_usd": 0.0,
        "window_count": len(usages),
    }
    for usage in usages:
        totals["input_tokens"] += int(usage.input_tokens)
        totals["output_tokens"] += int(usage.output_tokens)
        totals["cache_read_tokens"] += int(usage.cache_read_tokens)
        totals["cache_write_tokens"] += int(usage.cache_write_tokens)
        totals["latency_ms"] += int(usage.latency_ms)
        totals["cost_usd"] = round(totals["cost_usd"] + float(usage.cost_usd), 6)
    totals["windows"] = [
        {
            "window_index": u.window_index,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read_tokens": u.cache_read_tokens,
            "cache_write_tokens": u.cache_write_tokens,
            "latency_ms": u.latency_ms,
            "cost_usd": round(u.cost_usd, 6),
            "attempt": u.attempt,
        }
        for u in usages
    ]
    return totals
