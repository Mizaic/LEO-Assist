"""Aggregate spancat predictions across overlapping transformer windows.

Atlas trace:
  DO: DO-A00CD165
  DI: DI-3FDBB57B

Clinical sentences routinely exceed the Bio_ClinicalBERT 512-token context.
With strided spans (``window = 256``, ``stride = 192``), a single span can be
scored in multiple windows. spaCy's built-in SpanCategorizer returns one row
per (window, candidate); collapsing across windows is left to the caller.

This module provides :func:`aggregate_strided_spans` which merges per-window
scores by taking the max score per unique ``(start, end, label)`` triple.
Empirically this outperforms mean/sum on our validation set because the
true-positive window tends to have a substantially higher score than partial
coverage windows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AggregatedSpan:
    start: int
    end: int
    label: str
    score: float


def aggregate_strided_spans(
    candidates: Iterable[tuple[int, int, str, float]],
    *,
    reducer: str = "max",
) -> list[AggregatedSpan]:
    """Collapse per-window (start, end, label, score) tuples into unique spans.

    Args:
        candidates: Iterable of ``(start, end, label, score)`` rows — one per
            (window, candidate).
        reducer: ``"max"`` (default) or ``"mean"``. Max is typically best for
            clinical corpora with small strides.
    """
    buckets: dict[tuple[int, int, str], list[float]] = defaultdict(list)
    for start, end, label, score in candidates:
        key = (int(start), int(end), str(label))
        buckets[key].append(float(score))

    out: list[AggregatedSpan] = []
    for (start, end, label), scores in buckets.items():
        if not scores:
            continue
        if reducer == "mean":
            reduced = sum(scores) / len(scores)
        else:
            reduced = max(scores)
        out.append(AggregatedSpan(start=start, end=end, label=label, score=reduced))
    out.sort(key=lambda s: (-s.score, s.start, s.end))
    return out
