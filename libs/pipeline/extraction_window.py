"""Policy-driven extraction window planner and merge (C3.1-C3.3)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChunkRef:
    chunk_id: str
    text: str = ""


@dataclass(frozen=True)
class ExtractionWindow:
    index: int
    chunk_ids: tuple[str, ...]
    input_hash: str


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


def plan_extraction_windows(
    chunks: list[ChunkRef],
    *,
    window_size: int = 10,
    window_overlap: int = 1,
) -> list[ExtractionWindow]:
    """Plan ordered windows from pinned policy defaults."""
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
        payload = "|".join(f"{cid}:{texts.get(cid, '')}" for cid in window_ids)
        windows.append(
            ExtractionWindow(
                index=idx,
                chunk_ids=window_ids,
                input_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            )
        )
        idx += 1
        if start + window_size >= len(ids):
            break
        start += step
    return windows


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
