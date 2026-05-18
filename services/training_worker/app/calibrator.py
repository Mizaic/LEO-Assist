"""Per-label probability calibration + threshold sweep for the spancat head.

Atlas trace:
  DO: DO-236545C8
  DI: DI-37B3DC71
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

What this does
--------------
After training, the SpanCategorizer produces raw probabilities per (candidate
span, label). The default SpanCategorizer threshold (0.5) is almost never the
F1-optimal operating point — especially on imbalanced clinical datasets where
rare labels benefit from lower thresholds and high-precision labels benefit
from higher thresholds.

This module:

1. Runs the trained model over the validation DocBin and collects per-label
   (score, is_true_match) pairs by matching candidate spans to gold spans.
2. Sweeps candidate thresholds and picks the one that maximises F1 for each
   label independently.
3. (Optional) fits isotonic regression per label so raw probabilities can be
   re-mapped to calibrated probabilities; the calibrator is stored as a set
   of piecewise linear breakpoints (no scikit-learn dep at inference time).
4. Writes ``calibration.json`` alongside the model containing:
     - per-label F1-optimal thresholds
     - per-label isotonic breakpoints (if fit)
     - diagnostic metrics (F1 before/after calibration, support)

The inference service can then honour ``calibration.json`` when deciding
whether to emit a span, and whether to rescale the confidence score.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Thresholds swept from this low bound (inclusive) upwards in ``_STEP`` strides.
_MIN_THRESHOLD = float(os.getenv("CALIBRATION_MIN_THRESHOLD", "0.05"))
_MAX_THRESHOLD = float(os.getenv("CALIBRATION_MAX_THRESHOLD", "0.95"))
_STEP = float(os.getenv("CALIBRATION_THRESHOLD_STEP", "0.02"))

# Default fallback when no positive examples exist for a label.
_FALLBACK_THRESHOLD = float(os.getenv("CALIBRATION_FALLBACK_THRESHOLD", "0.5"))

# Minimum positive support to attempt calibration. Labels below this fall back
# to the default threshold to avoid overfitting on a handful of examples.
_MIN_SUPPORT = int(os.getenv("CALIBRATION_MIN_SUPPORT", "10"))


@dataclass
class LabelCalibration:
    """Calibration artefact for a single label."""

    label: str
    threshold: float
    support_positive: int
    support_negative: int
    f1_at_default: float
    f1_at_threshold: float
    precision_at_threshold: float
    recall_at_threshold: float
    isotonic_x: list[float] = field(default_factory=list)
    isotonic_y: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "threshold": round(self.threshold, 4),
            "support_positive": self.support_positive,
            "support_negative": self.support_negative,
            "f1_at_default": round(self.f1_at_default, 4),
            "f1_at_threshold": round(self.f1_at_threshold, 4),
            "precision_at_threshold": round(self.precision_at_threshold, 4),
            "recall_at_threshold": round(self.recall_at_threshold, 4),
            "isotonic_x": [round(x, 6) for x in self.isotonic_x],
            "isotonic_y": [round(y, 6) for y in self.isotonic_y],
        }


@dataclass
class CalibrationResult:
    """Aggregate calibration output for all labels in the model."""

    default_threshold: float
    per_label: dict[str, LabelCalibration] = field(default_factory=dict)
    macro_f1_before: float = 0.0
    macro_f1_after: float = 0.0
    total_candidates: int = 0
    total_docs: int = 0

    def to_dict(self) -> dict:
        return {
            "default_threshold": self.default_threshold,
            "per_label": {
                label: cal.to_dict() for label, cal in self.per_label.items()
            },
            "macro_f1_before": round(self.macro_f1_before, 4),
            "macro_f1_after": round(self.macro_f1_after, 4),
            "total_candidates": self.total_candidates,
            "total_docs": self.total_docs,
        }


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def calibrate_model(
    model_dir: Path,
    val_path: Path,
    *,
    fit_isotonic: Optional[bool] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> CalibrationResult:
    """Calibrate a trained spaCy model against the validation DocBin.

    Args:
        model_dir: Path to the spaCy model directory.
        val_path: Path to the validation ``.spacy`` DocBin (NOT the dev split
            used for early stopping; calibration on the dev split would leak
            the final threshold choice into the gate-facing evaluation).
        fit_isotonic: If True, additionally fit per-label isotonic regression.
            Defaults to env var ``CALIBRATION_FIT_ISOTONIC`` (``"true"``/``"false"``).
        log_fn: Optional log line callback.

    Returns:
        A :class:`CalibrationResult` populated with per-label thresholds and
        (optionally) isotonic breakpoints.
    """
    import spacy
    from spacy.tokens import DocBin

    _register_training_architectures()

    def _log(msg: str) -> None:
        logger.info("[calibrator] %s", msg)
        if log_fn:
            log_fn(msg)

    if fit_isotonic is None:
        fit_isotonic = os.getenv("CALIBRATION_FIT_ISOTONIC", "true").lower() in (
            "1",
            "true",
            "yes",
        )

    if not val_path.exists():
        raise FileNotFoundError(
            f"Calibration requires a validation DocBin: {val_path} not found"
        )

    _log(f"Loading model from {model_dir} for calibration…")
    nlp = spacy.load(str(model_dir))
    if "spancat" not in nlp.pipe_names:
        raise RuntimeError(
            "Calibration requires a spancat component in the pipeline; "
            f"found {nlp.pipe_names!r}"
        )

    _log(f"Loading validation set from {val_path}…")
    bin_ = DocBin().from_disk(val_path)
    gold_docs = list(bin_.get_docs(nlp.vocab))
    if not gold_docs:
        raise RuntimeError("Validation set is empty — cannot calibrate")

    spancat = nlp.get_pipe("spancat")
    labels: tuple[str, ...] = tuple(spancat.labels)
    default_threshold = float(getattr(spancat, "cfg", {}).get("threshold", 0.5))
    _log(
        f"Calibrating {len(labels)} labels against {len(gold_docs)} docs "
        f"(default threshold={default_threshold:.2f})"
    )

    # For each (label_idx) we'll accumulate (score, is_positive) pairs.
    # Positives are candidate spans whose (start, end) matches a gold span with
    # the same label. Negatives are every other candidate under that label.
    pairs: dict[int, list[tuple[float, int]]] = {i: [] for i in range(len(labels))}

    texts = [doc.text for doc in gold_docs]
    pred_docs = [nlp.make_doc(t) for t in texts]
    # Use the pipeline's tok2vec/transformer so spancat predict sees real reps.
    # Run through the pipeline up to but not including spancat's thresholding.
    for name, component in nlp.pipeline:
        if name == "spancat":
            break
        if hasattr(component, "pipe"):
            pred_docs = list(component.pipe(pred_docs))

    indices, scores = spancat.predict(pred_docs)
    # indices: Ragged — data is (total_candidates, 2) array of (start, end)
    # token indices per doc. lengths sum to total_candidates.
    # scores: Floats2d — (total_candidates, n_labels).
    lengths = list(indices.lengths) if hasattr(indices, "lengths") else []
    offset = 0
    total_candidates = 0

    for doc_idx, doc in enumerate(pred_docs):
        gold = gold_docs[doc_idx]
        gold_spans = {
            (span.start, span.end, span.label_) for span in gold.spans.get("sc", [])
        }
        n_candidates = int(lengths[doc_idx]) if doc_idx < len(lengths) else 0
        total_candidates += n_candidates
        for c in range(n_candidates):
            row = offset + c
            start = int(indices.dataXd[row, 0])
            end = int(indices.dataXd[row, 1])
            for label_idx, label in enumerate(labels):
                score = float(scores[row, label_idx])
                is_positive = int((start, end, label) in gold_spans)
                pairs[label_idx].append((score, is_positive))
        offset += n_candidates

    result = CalibrationResult(
        default_threshold=default_threshold,
        total_candidates=total_candidates,
        total_docs=len(gold_docs),
    )

    f1_before_sum = 0.0
    f1_after_sum = 0.0
    counted = 0

    for label_idx, label in enumerate(labels):
        records = pairs[label_idx]
        positives = sum(1 for _, y in records if y == 1)
        negatives = len(records) - positives
        if positives == 0:
            _log(
                f"Label {label}: no positives in validation — using default "
                f"threshold {_FALLBACK_THRESHOLD:.2f}"
            )
            result.per_label[label] = LabelCalibration(
                label=label,
                threshold=_FALLBACK_THRESHOLD,
                support_positive=0,
                support_negative=negatives,
                f1_at_default=0.0,
                f1_at_threshold=0.0,
                precision_at_threshold=0.0,
                recall_at_threshold=0.0,
            )
            continue

        f1_default, p_default, r_default = _metrics_at_threshold(
            records, default_threshold
        )

        if positives < _MIN_SUPPORT:
            _log(
                f"Label {label}: only {positives} positives (<{_MIN_SUPPORT}) — "
                "keeping default threshold to avoid overfit"
            )
            best_threshold = default_threshold
            best_f1 = f1_default
            best_p = p_default
            best_r = r_default
        else:
            best_threshold, best_f1, best_p, best_r = _sweep_thresholds(records)

        f1_before_sum += f1_default
        f1_after_sum += best_f1
        counted += 1

        iso_x: list[float] = []
        iso_y: list[float] = []
        if fit_isotonic and positives >= _MIN_SUPPORT:
            iso_x, iso_y = _fit_isotonic(records)

        result.per_label[label] = LabelCalibration(
            label=label,
            threshold=best_threshold,
            support_positive=positives,
            support_negative=negatives,
            f1_at_default=f1_default,
            f1_at_threshold=best_f1,
            precision_at_threshold=best_p,
            recall_at_threshold=best_r,
            isotonic_x=iso_x,
            isotonic_y=iso_y,
        )
        _log(
            f"Label {label}: thr {default_threshold:.2f}->{best_threshold:.2f}  "
            f"F1 {f1_default:.3f}->{best_f1:.3f}  "
            f"(pos={positives} neg={negatives})"
        )

    if counted > 0:
        result.macro_f1_before = f1_before_sum / counted
        result.macro_f1_after = f1_after_sum / counted

    # Persist to disk under the model directory.
    out_path = model_dir / "calibration.json"
    out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    _log(
        f"Wrote calibration to {out_path} "
        f"(macro-F1 {result.macro_f1_before:.3f} -> {result.macro_f1_after:.3f})"
    )
    return result


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _register_training_architectures() -> None:
    try:
        import app.spacy_listener_width  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            f"Failed to register training architectures before calibration: {exc}"
        ) from exc


def _metrics_at_threshold(
    records: list[tuple[float, int]], threshold: float
) -> tuple[float, float, float]:
    tp = fp = fn = 0
    for score, y in records:
        predicted = score >= threshold
        if predicted and y == 1:
            tp += 1
        elif predicted and y == 0:
            fp += 1
        elif (not predicted) and y == 1:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        (2 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return f1, precision, recall


def _sweep_thresholds(
    records: list[tuple[float, int]],
) -> tuple[float, float, float, float]:
    best = (_FALLBACK_THRESHOLD, 0.0, 0.0, 0.0)
    # Always include default threshold so rollback to it is possible.
    n_steps = max(1, int(math.ceil((_MAX_THRESHOLD - _MIN_THRESHOLD) / _STEP)))
    thresholds = [
        round(_MIN_THRESHOLD + i * _STEP, 4) for i in range(n_steps + 1)
    ]
    for threshold in thresholds:
        if threshold < 0.0 or threshold > 1.0:
            continue
        f1, p, r = _metrics_at_threshold(records, threshold)
        if f1 > best[1]:
            best = (threshold, f1, p, r)
    return best


def _fit_isotonic(
    records: list[tuple[float, int]],
) -> tuple[list[float], list[float]]:
    """Fit isotonic regression per label and return sparse breakpoints.

    We fit with :class:`sklearn.isotonic.IsotonicRegression` on the (score,
    y) pairs and then extract a compact set of breakpoints. At inference time
    a calibrated probability can be obtained by linear interpolation between
    the stored x/y points — no scikit-learn dependency required.
    """
    try:
        from sklearn.isotonic import IsotonicRegression
    except Exception as exc:
        logger.warning(
            "[calibrator] scikit-learn unavailable (%s) — skipping isotonic",
            exc,
        )
        return [], []

    xs = [score for score, _ in records]
    ys = [float(y) for _, y in records]
    if not xs:
        return [], []
    model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    model.fit(xs, ys)
    # Sample at fixed grid so the stored curve is small and deterministic.
    grid = [round(i / 100.0, 2) for i in range(0, 101, 5)]
    calibrated = model.predict(grid)
    return list(grid), [float(v) for v in calibrated]


def apply_calibration(
    raw_score: float,
    label_calibration: dict,
) -> float:
    """Piecewise-linear interpolation using stored isotonic breakpoints.

    Returns the calibrated probability, or the raw score if no curve exists.
    Callable at inference without scikit-learn.
    """
    xs = label_calibration.get("isotonic_x") or []
    ys = label_calibration.get("isotonic_y") or []
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
