"""Stage 12 - NCDA detector evaluation harness.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Pure metric functions consumed by:
  - scripts/ncda/evaluate.py (the runnable evaluation script).
  - services/training_worker/app/jobs/ncda_nightly.py (gating promotion).
  - tests/ncda/test_metrics_baseline.py (locked baselines).

All inputs are simple lists/dicts so unit testing is straightforward.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RoleMetric:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


def per_role_metrics(
    y_true: list[str], y_pred: list[str]
) -> dict[str, dict[str, float]]:
    """Per-role precision/recall/F1 (no sklearn dep at runtime)."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have equal length.")
    labels = sorted(set(y_true) | set(y_pred))
    metrics: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = fp = fn = 0
        for t, p in zip(y_true, y_pred):
            if t == label and p == label:
                tp += 1
            elif p == label and t != label:
                fp += 1
            elif t == label and p != label:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        metrics[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(1 for t in y_true if t == label),
        }
    return metrics


def per_cohort_metrics(
    y_true: list[str], y_pred: list[str]
) -> dict[str, dict[str, float]]:
    """Same shape as per_role_metrics but keyed by cohort identifier."""
    return per_role_metrics(y_true, y_pred)


def days_error(predicted: Iterable[int], gold: Iterable[int]) -> dict[str, float]:
    """Mean absolute / median / max days-error between paired sequences."""
    pairs = list(zip(predicted, gold))
    if not pairs:
        return {"mae": 0.0, "median": 0.0, "max": 0.0, "n": 0}
    diffs = sorted(abs(int(p) - int(g)) for p, g in pairs)
    mae = sum(diffs) / len(diffs)
    mid = diffs[len(diffs) // 2]
    return {"mae": round(mae, 3), "median": float(mid), "max": float(diffs[-1]), "n": len(diffs)}


def breach_flag_accuracy(
    predicted: list[bool], gold: list[bool]
) -> dict[str, float]:
    """Accuracy on boolean breach flags (e.g. FDS-28, treatment-31)."""
    if not predicted:
        return {"accuracy": 0.0, "n": 0}
    correct = sum(1 for p, g in zip(predicted, gold) if bool(p) == bool(g))
    return {"accuracy": round(correct / len(predicted), 4), "n": len(predicted)}


def coverage(
    recovered_pair_ids: Iterable[str], gold_pair_ids: Iterable[str]
) -> float:
    gold = set(gold_pair_ids)
    if not gold:
        return 1.0
    found = set(recovered_pair_ids) & gold
    return round(len(found) / len(gold), 4)


def false_alarm_rate_cohort_3(
    predicted_cohort_3_ids: Iterable[str], gold_cohort_3_ids: Iterable[str]
) -> float:
    """Proportion of predicted cohort-3 patients that are NOT in the gold set."""
    predicted = list(predicted_cohort_3_ids)
    if not predicted:
        return 0.0
    gold = set(gold_cohort_3_ids)
    false = sum(1 for p in predicted if p not in gold)
    return round(false / len(predicted), 4)


def evaluate(
    *,
    role_y_true: list[str],
    role_y_pred: list[str],
    cohort_y_true: list[str],
    cohort_y_pred: list[str],
    ftr_dx_days_pred: list[int],
    ftr_dx_days_gold: list[int],
    breach_flags_pred: list[bool],
    breach_flags_gold: list[bool],
    pair_recovered_ids: list[str],
    pair_gold_ids: list[str],
    predicted_cohort_3_ids: list[str],
    gold_cohort_3_ids: list[str],
) -> dict:
    """Run the full evaluation suite and return a single metrics payload."""
    return {
        "role_metrics": per_role_metrics(role_y_true, role_y_pred),
        "cohort_metrics": per_cohort_metrics(cohort_y_true, cohort_y_pred),
        "days_error": {
            "ftr_to_dx": days_error(ftr_dx_days_pred, ftr_dx_days_gold),
        },
        "breach_flag_accuracy": breach_flag_accuracy(breach_flags_pred, breach_flags_gold),
        "coverage": coverage(pair_recovered_ids, pair_gold_ids),
        "cohort_3_false_alarm_rate": false_alarm_rate_cohort_3(
            predicted_cohort_3_ids, gold_cohort_3_ids
        ),
    }
