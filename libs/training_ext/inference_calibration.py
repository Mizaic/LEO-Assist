"""Inference-time helpers for per-label thresholds and isotonic calibration.

Atlas trace:
  DO: DO-54397CCD, DO-A00CD165
  DI: DI-3FDBB57B

Consumed by the model inference service. Loads ``calibration.json`` (written
during training by ``calibrator.py``) and exposes:

* :func:`load_calibration(model_dir)` — reads and validates the payload
  against the bundle manifest.
* :func:`filter_and_rescore(spans, calibration)` — drops spans below their
  per-label threshold and (if isotonic breakpoints exist) rescales the raw
  probability to a calibrated one.

The inference service keeps the calibration alongside the loaded spaCy model
so a hot-swap atomically replaces both thresholds and the model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from libs.training_ext.bundle import verify_bundle

logger = logging.getLogger(__name__)


@dataclass
class InferenceCalibration:
    """Runtime view of calibration.json."""

    default_threshold: float = 0.5
    per_label: dict[str, dict] = field(default_factory=dict)
    is_verified: bool = False

    def threshold_for(self, label: str) -> float:
        entry = self.per_label.get(label.upper())
        if not entry:
            return self.default_threshold
        return float(entry.get("threshold", self.default_threshold))

    def calibrate(self, label: str, raw_score: float) -> float:
        """Return the calibrated score for a raw probability."""
        entry = self.per_label.get(label.upper()) or {}
        xs = entry.get("isotonic_x") or []
        ys = entry.get("isotonic_y") or []
        if len(xs) < 2 or len(xs) != len(ys):
            return raw_score
        if raw_score <= xs[0]:
            return ys[0]
        if raw_score >= xs[-1]:
            return ys[-1]
        for i in range(1, len(xs)):
            if raw_score <= xs[i]:
                lo_x, hi_x = xs[i - 1], xs[i]
                lo_y, hi_y = ys[i - 1], ys[i]
                if hi_x == lo_x:
                    return hi_y
                frac = (raw_score - lo_x) / (hi_x - lo_x)
                return lo_y + frac * (hi_y - lo_y)
        return raw_score


def load_calibration(model_dir: Path) -> InferenceCalibration:
    """Load calibration.json from a model bundle, verifying the manifest."""
    calib_path = model_dir / "calibration.json"
    if not calib_path.exists():
        logger.info("[inference-cal] No calibration.json in %s", model_dir)
        return InferenceCalibration()

    discrepancies = verify_bundle(model_dir)
    is_verified = not discrepancies
    if discrepancies:
        logger.warning(
            "[inference-cal] Bundle manifest mismatch (%d entries) — "
            "falling back to raw probabilities: %s",
            len(discrepancies),
            "; ".join(discrepancies[:3]),
        )

    try:
        payload = json.loads(calib_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[inference-cal] Could not parse calibration.json: %s", exc)
        return InferenceCalibration()

    default_threshold = float(payload.get("default_threshold", 0.5))
    per_label_raw = payload.get("per_label") or {}
    per_label = {label.upper(): cal for label, cal in per_label_raw.items()}
    return InferenceCalibration(
        default_threshold=default_threshold,
        per_label=per_label,
        is_verified=is_verified,
    )


@dataclass
class FilteredSpan:
    """What we hand back to the inference service."""

    label: str
    start_char: int
    end_char: int
    text: str
    raw_score: float
    calibrated_score: float


def filter_and_rescore(
    spans: Iterable,
    calibration: InferenceCalibration,
    *,
    include_below_threshold: bool = False,
) -> list[FilteredSpan]:
    """Apply per-label thresholds and return surviving spans.

    Spans are expected to be spaCy Span-like objects with ``label_``,
    ``start_char``, ``end_char``, ``text``, and ``kb_id_`` (confidence in our
    pipeline). When ``include_below_threshold`` is True, spans below threshold
    are still returned but marked by the caller — useful for the active
    learning review queue.
    """
    out: list[FilteredSpan] = []
    if calibration is None or not calibration.is_verified and not calibration.per_label:
        calibration = calibration or InferenceCalibration()
    span_items = list(spans)
    group_scores = _span_group_scores(spans)
    for index, span in enumerate(span_items):
        label = str(span.label_).upper()
        raw = _raw_score(
            span,
            fallback_score=group_scores[index] if index < len(group_scores) else None,
        )
        threshold = calibration.threshold_for(label)
        if raw < threshold and not include_below_threshold:
            continue
        calibrated = calibration.calibrate(label, raw)
        out.append(
            FilteredSpan(
                label=label,
                start_char=int(span.start_char),
                end_char=int(span.end_char),
                text=str(span.text),
                raw_score=round(raw, 4),
                calibrated_score=round(calibrated, 4),
            )
        )
    return out


def _span_group_scores(spans: Iterable) -> list[float]:
    """Return spaCy SpanGroup scores when present.

    SpanCategorizer stores probabilities on ``doc.spans["sc"].attrs["scores"]``
    rather than on each Span. Older NER-style paths may still place confidence
    on ``span.kb_id_``, so these scores are only used as a fallback.
    """
    attrs = getattr(spans, "attrs", {}) or {}
    raw_scores = attrs.get("scores")
    if raw_scores is None:
        return []
    try:
        return [float(score) for score in raw_scores]
    except TypeError:
        return []


def _raw_score(span, *, fallback_score: float | None = None) -> float:
    raw = getattr(span, "kb_id_", "") or ""
    try:
        return float(raw)
    except ValueError:
        return float(fallback_score) if fallback_score is not None else 0.0
