"""Training quality gates for multi-label clinical extraction models.

Atlas trace:
  DO: DO-93E0D02E
  DI: DI-3FEEA0AD
  VT: VT-0C4840D3
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_EXPECTED_LABELS: tuple[str, ...] = (
    "PROCEDURE",
    "OBSERVABLE",
    "FINDING",
)

_LABEL_ALIASES: dict[str, str] = {
    "OBSERVABLE_ENTITY": "OBSERVABLE",
    "QUALIFIER_VALUE": "QUALIFIER",
    "X_TEMPORAL": "TEMPORAL",
    "X_DOSAGE": "DOSAGE",
    "X_FREQUENCY": "FREQUENCY",
    "X_ROUTE": "ROUTE",
}


def expected_labels_from_env() -> tuple[str, ...]:
    """Return labels that must be represented for a safe training run."""
    raw = os.getenv("TRAINING_EXPECTED_LABELS", "")
    if not raw.strip():
        return DEFAULT_EXPECTED_LABELS
    return tuple(_normalise_label(v) for v in raw.split(",") if v.strip())


def min_training_support_from_env() -> int:
    """Return minimum total examples per expected label."""
    return _env_int("TRAINING_MIN_LABEL_SUPPORT", 30)


def min_evaluated_labels_from_env() -> int:
    """Return minimum number of expected labels that must be evaluated."""
    return _env_int("MODEL_MIN_EVALUATED_LABELS", 2)


def min_macro_f1_from_env() -> float:
    """Return optional macro-F1 floor for model evaluation."""
    return _env_float("MODEL_MIN_MACRO_F1", 0.0)


def summarise_export_support(
    per_label_counts: dict[str, dict[str, int]],
    *,
    expected_labels: tuple[str, ...] | None = None,
    min_support: int | None = None,
) -> dict[str, Any]:
    """Summarise export support and flag under-represented expected labels."""
    expected = tuple(_normalise_label(label) for label in (
        expected_labels or expected_labels_from_env()
    ))
    threshold = min_training_support_from_env() if min_support is None else min_support
    totals = {
        _normalise_label(label): sum(int(v or 0) for v in splits.values())
        for label, splits in per_label_counts.items()
    }
    missing = [label for label in expected if totals.get(label, 0) == 0]
    low_support = {
        label: totals.get(label, 0)
        for label in expected
        if 0 < totals.get(label, 0) < threshold
    }
    return {
        "expected_labels": list(expected),
        "observed_labels": sorted(totals),
        "support_total": dict(sorted(totals.items())),
        "min_support": threshold,
        "missing_expected_labels": missing,
        "low_support_expected_labels": low_support,
        "passed": not missing and not low_support,
    }


def macro_f1(per_label: dict[str, dict[str, Any]]) -> float:
    """Return unweighted macro F1 over labels with numeric F1 values."""
    values = [
        _safe_float(row.get("f1"))
        for row in per_label.values()
        if row.get("f1") is not None
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def evaluate_label_coverage(
    per_label: dict[str, dict[str, Any]],
    *,
    expected_labels: tuple[str, ...] | None = None,
    min_evaluated_labels: int | None = None,
    min_macro_f1: float | None = None,
) -> dict[str, Any]:
    """Return pass/fail coverage checks for model evaluation metrics."""
    expected = tuple(_normalise_label(label) for label in (
        expected_labels or expected_labels_from_env()
    ))
    evaluated = {_normalise_label(label) for label in per_label}
    missing = [label for label in expected if label not in evaluated]
    observed_expected = sorted(label for label in expected if label in evaluated)
    min_labels = (
        min_evaluated_labels_from_env()
        if min_evaluated_labels is None
        else min_evaluated_labels
    )
    macro = macro_f1(per_label)
    macro_floor = min_macro_f1_from_env() if min_macro_f1 is None else min_macro_f1
    failures: list[str] = []
    if len(observed_expected) < min_labels:
        failures.append(
            f"evaluated_expected_labels={len(observed_expected)} < min {min_labels}"
        )
    if missing:
        failures.append("missing expected labels: " + ", ".join(missing))
    if macro < macro_floor:
        failures.append(f"macro_f1={macro:.3f} < min {macro_floor:.2f}")
    return {
        "expected_labels": list(expected),
        "evaluated_expected_labels": observed_expected,
        "missing_expected_labels": missing,
        "min_evaluated_labels": min_labels,
        "macro_f1": macro,
        "min_macro_f1": macro_floor,
        "failures": failures,
        "passed": not failures,
    }


def _normalise_label(label: object) -> str:
    normalised = str(label or "").strip().upper().replace(" ", "_").replace("/", "_")
    return _LABEL_ALIASES.get(normalised, normalised)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
