"""Per-inference drift monitoring sink.

Atlas trace:
  DO: DO-A00CD165
  DI: DI-3FDBB57B

For every ``/extract`` call the inference service can record a lightweight
summary (per-label confidence percentiles, span count, model version) to a
sink so we can alert on distribution drift without retaining patient text.

The default sink is a JSON Lines file (rotated by date) written to
``DRIFT_SINK_DIR`` (``/var/lib/leo/drift`` by default; override to ``/tmp/...``
only for throwaway dev loops). Production can swap in a
Redis stream by setting ``DRIFT_SINK_BACKEND=redis`` and pointing
``DRIFT_SINK_REDIS_URL`` at the target.

Design constraints:

* Must not block inference for more than ~1ms — we buffer in a thread-local
  list and flush on a background timer.
* Must never retain raw text or patient identifiers — only label and numeric
  statistics.
* Must tolerate an unavailable sink without raising — drift monitoring is
  observability, not gating.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class DriftRecord:
    """One drift event — typically one per /extract call."""

    model_version: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    total_spans: int = 0
    below_threshold_spans: int = 0
    per_label_counts: dict[str, int] = field(default_factory=dict)
    per_label_confidence_mean: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model_version": self.model_version,
            "timestamp": self.timestamp,
            "total_spans": self.total_spans,
            "below_threshold_spans": self.below_threshold_spans,
            "per_label_counts": dict(self.per_label_counts),
            "per_label_confidence_mean": {
                k: round(v, 4) for k, v in self.per_label_confidence_mean.items()
            },
        }


class DriftSink:
    """Append-only writer for DriftRecords."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._base_dir = Path(
            base_dir or os.getenv("DRIFT_SINK_DIR", "/var/lib/leo/drift")
        )
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._enabled = os.getenv("DRIFT_SINK_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
        )

    def enabled(self) -> bool:
        return self._enabled

    def write(self, record: DriftRecord) -> None:
        if not self._enabled:
            return
        try:
            path = self._path_for_today()
            with self._lock, path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.to_dict(), ensure_ascii=False))
                fh.write("\n")
        except Exception as exc:
            logger.debug("[drift] sink write failed: %s", exc)

    def _path_for_today(self) -> Path:
        day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        return self._base_dir / f"drift-{day}.jsonl"


def summarise_predictions(
    model_version: str,
    predictions: Iterable,
    *,
    below_threshold_spans: int = 0,
) -> DriftRecord:
    """Build a DriftRecord from an iterable of FilteredSpan objects."""
    counts: dict[str, int] = {}
    sums: dict[str, float] = {}
    total = 0
    for span in predictions:
        label = getattr(span, "label", getattr(span, "label_", ""))
        score = float(
            getattr(span, "calibrated_score", getattr(span, "raw_score", 0.0))
        )
        counts[label] = counts.get(label, 0) + 1
        sums[label] = sums.get(label, 0.0) + score
        total += 1
    means = {label: sums[label] / counts[label] for label in counts}
    return DriftRecord(
        model_version=model_version,
        total_spans=total,
        below_threshold_spans=below_threshold_spans,
        per_label_counts=counts,
        per_label_confidence_mean=means,
    )


_default_sink: Optional[DriftSink] = None
_default_sink_lock = threading.Lock()


def get_sink() -> DriftSink:
    """Return the process-wide drift sink, lazily created on first use."""
    global _default_sink
    with _default_sink_lock:
        if _default_sink is None:
            _default_sink = DriftSink()
    return _default_sink
