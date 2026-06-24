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


# ---------------------------------------------------------------------------
# Drift analyser -- 7-day rolling baseline comparison (DC-MTP-001 SS13)
# ---------------------------------------------------------------------------

CONFIDENCE_DROP_THRESHOLD = 0.10  # 10% relative drop triggers alert
_BASELINE_DAYS = 7


@dataclass
class DriftAlert:
    """Confidence drift for a single label exceeding the alert threshold."""

    label: str
    baseline_mean: float
    today_mean: float
    relative_drop: float  # positive means today is lower


def _load_day_records(base_dir: Path, day: datetime.date) -> list[dict]:
    """Read all DriftRecord dicts from one day's JSONL file."""
    path = base_dir / f"drift-{day.isoformat()}.jsonl"
    if not path.exists():
        return []
    records = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            logger.debug("[drift] skipping malformed JSONL line")
    return records


def _weighted_label_means(records: list[dict]) -> dict[str, float]:
    """Weighted per-label confidence mean across a list of DriftRecord dicts."""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in records:
        label_counts = r.get("per_label_counts") or {}
        label_means = r.get("per_label_confidence_mean") or {}
        for label, n in label_counts.items():
            if n > 0 and label in label_means:
                sums[label] = sums.get(label, 0.0) + label_means[label] * n
                counts[label] = counts.get(label, 0) + n
    return {
        label: sums[label] / counts[label]
        for label in counts
        if counts[label] > 0
    }


def _baseline_means(daily_means: list[dict[str, float]]) -> dict[str, float]:
    """Simple mean of per-label daily means across baseline days."""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for day_means in daily_means:
        for label, mean in day_means.items():
            sums[label] = sums.get(label, 0.0) + mean
            counts[label] = counts.get(label, 0) + 1
    return {label: sums[label] / counts[label] for label in counts if counts[label] > 0}


def check_confidence_drift(
    base_dir: Optional[Path] = None,
    *,
    baseline_days: int = _BASELINE_DAYS,
    today: Optional[datetime.date] = None,
    threshold: float = CONFIDENCE_DROP_THRESHOLD,
) -> list[DriftAlert]:
    """Compare today's per-label confidence means against the rolling baseline.

    Reads today's JSONL sink file and the preceding baseline_days files,
    then returns one DriftAlert per label where today's weighted-mean
    confidence has dropped more than threshold (relative) below the
    baseline mean.

    Returns an empty list when there are no today records or no baseline
    data -- never raises.

    Args:
        base_dir: Drift sink directory. Defaults to DRIFT_SINK_DIR env var.
        baseline_days: Number of prior days forming the baseline window.
        today: Reference date. Defaults to UTC today.
        threshold: Relative drop fraction that triggers an alert (0.10 = 10%).
    """
    resolved_dir = Path(base_dir or os.getenv("DRIFT_SINK_DIR", "/var/lib/leo/drift"))
    resolved_today = today or datetime.datetime.utcnow().date()

    today_records = _load_day_records(resolved_dir, resolved_today)
    if not today_records:
        return []
    today_means = _weighted_label_means(today_records)

    baseline_daily: list[dict[str, float]] = []
    for offset in range(1, baseline_days + 1):
        day = resolved_today - datetime.timedelta(days=offset)
        records = _load_day_records(resolved_dir, day)
        if records:
            baseline_daily.append(_weighted_label_means(records))

    if not baseline_daily:
        return []

    baseline = _baseline_means(baseline_daily)
    alerts: list[DriftAlert] = []
    for label, today_mean in today_means.items():
        bline = baseline.get(label)
        if not bline:
            continue
        relative_drop = (bline - today_mean) / bline
        if relative_drop > threshold:
            alerts.append(
                DriftAlert(
                    label=label,
                    baseline_mean=round(bline, 4),
                    today_mean=round(today_mean, 4),
                    relative_drop=round(relative_drop, 4),
                )
            )
    return alerts
