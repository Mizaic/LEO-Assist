"""Evaluate a compiled OBSERVATION leaf against a patient's observations.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")

Atlas trace (Phase 5d):
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    Risk: R-555C8691
    VT: VT-404C1E2C

This module is intentionally separate from ``guideline_evaluator`` so
the OBSERVATION-mode dispatch (absolute / temporal / reference_range /
trend / aggregate) can be unit-tested in isolation. The wider rule
engine just calls ``observation_matches(node, patient_observations,
patient_sex, patient_age)`` and gets a single bool back.

Wire shapes
-----------

A compiled OBSERVATION leaf is a dict like::

    {
        "kind": "observation",
        "observable_id": "365632008",
        "operator": ">=",
        "value": 400.0,                # canonical unit
        "unit": "10*9/L",              # canonical unit
        "wire_unit": "x10^9/L",        # what the rule was authored in
        "within_days": 365,
        "temporal": None,              # or a TemporalSpec dict
        "reference_range": None,       # or a ReferenceRangeSpec dict
        "trend": None,                 # or a TrendSpec dict
        "aggregation": None,           # or an AggregateSpec dict
    }

A patient observation is a dict like::

    {
        "observable_id": "365632008",
        "value": 482,
        "unit": "10*9/L",
        "observed_at": "2026-02-14T09:00:00+00:00",  # ISO-8601
    }

Fail-closed contract
--------------------

Every mode returns False when the data needed to answer the question
is missing -- no readings inside the recency window, no reference
range registered for the patient demographic, fewer than the required
number of readings for an aggregate, etc. This matches today's
behaviour for unrecognised demographic gates and is the safe default
for clinical decision support.

Errors during canonicalisation (unknown unit on a patient reading,
non-finite value) are also treated as 'no usable data' for that
reading -- the bad reading is dropped silently and an error is
logged. This stops one corrupt row from making a clinical rule fail
across an entire cohort.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from libs.lab_results.classifier import (
    LabConfigError,
    convert_value as convert_lab_value,
    get_lab_config,
    select_reference_range as select_lab_reference_range,
)
from libs.units.observable_units import (
    UnitConversionError,
    UnknownObservableError,
    canonicalise_value_for_observation,
    get_canonical_unit,
    get_reference_range,
)

logger = logging.getLogger(__name__)

# Reference clock used by every "within_days" calculation. Wall clock
# is fine for primary-care observables (the windows are days to years).
# Pulled out so tests can monkeypatch a fixed reference instant.
_NOW_FN: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

# Numeric tolerance for trend percent denominator -- anything closer to
# zero than this is treated as 'cannot compute percentage change' and
# fails closed.
_TREND_DENOMINATOR_EPSILON = 1e-9


@dataclass(frozen=True)
class _Reading:
    """A patient observation, canonicalised to the observable's unit."""

    canonical_value: float
    observed_at: datetime


def observation_matches(
    leaf: dict[str, Any],
    patient_observations: Iterable[dict[str, Any]] | None,
    *,
    patient_sex: str | None,
    patient_age: float | None,
    now: datetime | None = None,
    org_id: str | None = None,
) -> bool:
    """Return True when the OBSERVATION leaf fires for this patient.

    Args:
        leaf: Compiled OBSERVATION leaf (see module docstring).
        patient_observations: Iterable of patient observation rows.
            None or empty = patient has no observations on file at all,
            which fails closed in every mode.
        patient_sex: 'female' or 'male' (case-insensitive). Used by
            reference_range mode.
        patient_age: Decimal years. Used by reference_range mode.
        now: Override the reference instant for tests. Defaults to
            datetime.now(UTC).

    Returns:
        True if the rule's question is answered yes, False otherwise.
        Fails closed (False) when data is missing.
    """
    observable_id = leaf.get("observable_id")
    if not observable_id:
        logger.error(
            "OBSERVATION leaf %r missing observable_id at evaluation "
            "time -- failing CLOSED.",
            leaf.get("node_id"),
        )
        return False

    # Identify which mode this leaf is in. The compiler echoes exactly
    # one of these as a non-null dict; we honour them in the same
    # priority order the schema validator enforces (mutually exclusive
    # at authoring time).
    if leaf.get("temporal"):
        mode = "temporal"
    elif leaf.get("reference_range"):
        mode = "reference_range"
    elif leaf.get("trend"):
        mode = "trend"
    elif leaf.get("aggregation"):
        mode = "aggregate"
    else:
        mode = "absolute"

    reference_now = now or _NOW_FN()
    readings = _build_reading_window(
        observable_id,
        patient_observations,
        within_days=int(leaf.get("within_days") or 365),
        now=reference_now,
        rule_canonical_unit=str(leaf.get("unit") or ""),
    )

    if mode == "absolute":
        return _evaluate_absolute(leaf, readings)
    if mode == "temporal":
        return _evaluate_temporal(leaf, readings)
    if mode == "reference_range":
        return _evaluate_reference_range(
            leaf,
            readings,
            patient_sex=patient_sex,
            patient_age=patient_age,
            org_id=org_id,
        )
    if mode == "trend":
        return _evaluate_trend(leaf, readings, now=reference_now)
    if mode == "aggregate":
        return _evaluate_aggregate(leaf, readings)

    logger.error(
        "OBSERVATION leaf %r dispatched to unknown mode %r -- failing CLOSED.",
        leaf.get("node_id"),
        mode,
    )
    return False


# ---------------------------------------------------------------------------
# Mode dispatchers
# ---------------------------------------------------------------------------


def _evaluate_absolute(
    leaf: dict[str, Any],
    readings: list[_Reading],
) -> bool:
    """Mode: most-recent reading vs threshold."""
    if not readings:
        return False
    latest = readings[0]
    return _compare(latest.canonical_value, leaf.get("operator"), leaf.get("value"))


def _evaluate_temporal(
    leaf: dict[str, Any],
    readings: list[_Reading],
) -> bool:
    """Mode: N consecutive readings, each spaced by interval_min/max days."""
    spec = leaf.get("temporal") or {}
    count = int(spec.get("count") or 0)
    if count < 2:
        logger.error(
            "OBSERVATION temporal leaf %r has count < 2 -- failing CLOSED.",
            leaf.get("node_id"),
        )
        return False
    if len(readings) < count:
        return False

    operator = leaf.get("operator")
    value = leaf.get("value")
    interval_min_days = int(spec.get("interval_min_days") or 0)
    interval_max_days_raw = spec.get("interval_max_days")
    interval_max_days = (
        int(interval_max_days_raw) if interval_max_days_raw is not None else None
    )

    qualifying = [r for r in readings if _compare(r.canonical_value, operator, value)]
    if len(qualifying) < count:
        return False

    # Walk consecutive runs in chronological order. Readings come back
    # newest-first; reversing here keeps the interval check natural.
    chronological = list(reversed(qualifying))
    for start in range(len(chronological) - count + 1):
        window = chronological[start : start + count]
        if _intervals_satisfy(window, interval_min_days, interval_max_days):
            return True
    return False


def _evaluate_reference_range(
    leaf: dict[str, Any],
    readings: list[_Reading],
    *,
    patient_sex: str | None,
    patient_age: float | None,
    org_id: str | None = None,
) -> bool:
    """Mode: most-recent reading vs the patient's reference range bound."""
    if not readings:
        return False
    spec = leaf.get("reference_range") or {}
    bound_kind = str(spec.get("bound") or "upper").lower()
    multiple = float(spec.get("multiple_of_range") or 1.0)

    observable_id = str(leaf.get("observable_id") or "")
    config = get_lab_config(observable_id, org_id=org_id)
    band = (
        select_lab_reference_range(
            config.reference_ranges,
            sex=patient_sex,
            age_years=patient_age,
            org_id=org_id,
        )
        if config is not None
        else get_reference_range(
            observable_id,
            sex=patient_sex,
            age_years=patient_age,
        )
    )
    if band is None:
        logger.warning(
            "OBSERVATION reference_range leaf %r has no reference range "
            "for the patient demographic (sex=%r, age=%r) -- failing "
            "CLOSED.",
            leaf.get("node_id"),
            patient_sex,
            patient_age,
        )
        return False

    if bound_kind == "upper":
        bound_value = getattr(band, "upper", None)
        if bound_value is None:
            bound_value = getattr(band, "high", None)
    else:
        bound_value = getattr(band, "lower", None)
        if bound_value is None:
            bound_value = getattr(band, "low", None)
    if bound_value is None:
        logger.warning(
            "OBSERVATION reference_range leaf %r asks for the %s bound "
            "but the band has no %s value -- failing CLOSED.",
            leaf.get("node_id"),
            bound_kind,
            bound_kind,
        )
        return False

    threshold = bound_value * multiple
    return _compare(readings[0].canonical_value, leaf.get("operator"), threshold)


def _evaluate_trend(
    leaf: dict[str, Any],
    readings: list[_Reading],
    *,
    now: datetime,
) -> bool:
    """Mode: change in value from oldest-in-window to newest-in-window."""
    spec = leaf.get("trend") or {}
    window_days = int(spec.get("window_days") or 0)
    if window_days <= 0:
        logger.error(
            "OBSERVATION trend leaf %r has non-positive window_days -- failing CLOSED.",
            leaf.get("node_id"),
        )
        return False

    delta_kind = str(spec.get("delta_kind") or "absolute").lower()
    in_window = _filter_to_window(readings, window_days, now)
    if len(in_window) < 2:
        return False
    latest = in_window[0].canonical_value
    oldest = in_window[-1].canonical_value
    if delta_kind == "absolute":
        delta = latest - oldest
    elif delta_kind == "percent":
        denom = abs(oldest) if abs(oldest) > _TREND_DENOMINATOR_EPSILON else None
        if denom is None:
            logger.warning(
                "OBSERVATION trend percent leaf %r has near-zero "
                "baseline (oldest=%r) -- failing CLOSED.",
                leaf.get("node_id"),
                oldest,
            )
            return False
        delta = 100.0 * (latest - oldest) / denom
    else:
        logger.error(
            "OBSERVATION trend leaf %r has unknown delta_kind %r -- failing CLOSED.",
            leaf.get("node_id"),
            delta_kind,
        )
        return False
    return _compare(delta, leaf.get("operator"), leaf.get("value"))


def _evaluate_aggregate(
    leaf: dict[str, Any],
    readings: list[_Reading],
) -> bool:
    """Mode: aggregate of the last N readings vs threshold."""
    spec = leaf.get("aggregation") or {}
    lookback_n = int(spec.get("lookback_n") or 0)
    if lookback_n <= 0:
        logger.error(
            "OBSERVATION aggregate leaf %r has non-positive lookback_n -- failing CLOSED.",
            leaf.get("node_id"),
        )
        return False
    if len(readings) < lookback_n:
        return False
    window = [r.canonical_value for r in readings[:lookback_n]]
    kind = str(spec.get("kind") or "mean").lower()
    aggregate = _reduce_window(window, kind)
    if aggregate is None:
        return False
    return _compare(aggregate, leaf.get("operator"), leaf.get("value"))


# ---------------------------------------------------------------------------
# Reading-window construction helpers
# ---------------------------------------------------------------------------


def _build_reading_window(
    observable_id: str,
    raw_observations: Iterable[dict[str, Any]] | None,
    *,
    within_days: int,
    now: datetime,
    rule_canonical_unit: str,
) -> list[_Reading]:
    """Filter and canonicalise patient observations for one observable.

    Returns readings inside ``within_days`` of ``now``, sorted with the
    most recent first. Bad rows (unknown unit, non-finite value,
    missing timestamp) are dropped with a warning.
    """
    if raw_observations is None:
        return []
    cutoff = now - timedelta(days=max(int(within_days), 0))
    out: list[_Reading] = []
    for row in raw_observations:
        if str(row.get("observable_id") or "") != observable_id:
            continue
        observed_at = _coerce_datetime(row.get("observed_at"))
        if observed_at is None:
            logger.warning(
                "Patient observation row dropped: missing/invalid "
                "observed_at on observable %s.",
                observable_id,
            )
            continue
        if observed_at < cutoff:
            continue
        try:
            canonical = _canonicalise_reading_value(
                observable_id,
                row.get("value"),
                str(row.get("unit") or ""),
                rule_canonical_unit=rule_canonical_unit,
            )
        except (
            LabConfigError,
            UnknownObservableError,
            UnitConversionError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning(
                "Patient observation row dropped: cannot canonicalise "
                "(observable=%s, unit=%s): %s",
                observable_id,
                row.get("unit"),
                exc,
            )
            continue
        out.append(_Reading(canonical_value=canonical, observed_at=observed_at))
    out.sort(key=lambda r: r.observed_at, reverse=True)
    return out


def _canonicalise_reading_value(
    observable_id: str,
    value: Any,
    unit: str,
    *,
    rule_canonical_unit: str,
) -> float:
    config = get_lab_config(observable_id)
    if config is not None:
        return convert_lab_value(config, float(value), unit or config.canonical_unit)
    default_unit = rule_canonical_unit or get_canonical_unit(observable_id)
    return canonicalise_value_for_observation(
        observable_id,
        float(value),
        unit or default_unit,
        rule_canonical_unit=default_unit,
    )


def _filter_to_window(
    readings: list[_Reading],
    window_days: int,
    now: datetime,
) -> list[_Reading]:
    """Trim to readings inside the trend window (newest-first preserved)."""
    cutoff = now - timedelta(days=window_days)
    return [r for r in readings if r.observed_at >= cutoff]


def _coerce_datetime(raw: Any) -> datetime | None:
    """Parse a datetime from ISO-8601 string or pass through datetime objects.

    Returns None when the input is missing or unparseable. Naive
    datetimes are assumed to be UTC so the recency-window arithmetic
    is consistent.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


# ---------------------------------------------------------------------------
# Comparison + reduction primitives
# ---------------------------------------------------------------------------


def _compare(value: float, operator: Any, threshold: Any) -> bool:
    """Return True when ``value <op> threshold`` holds; False on bad input."""
    if value is None or operator is None or threshold is None:
        return False
    op = str(operator).strip()
    try:
        if op == "between":
            if not isinstance(threshold, (list, tuple)) or len(threshold) != 2:
                return False
            low, high = float(threshold[0]), float(threshold[1])
            return low <= float(value) <= high
        rhs = float(threshold)
        v = float(value)
    except (TypeError, ValueError):
        return False
    if op == ">=":
        return v >= rhs
    if op == "<=":
        return v <= rhs
    if op == ">":
        return v > rhs
    if op == "<":
        return v < rhs
    if op == "=":
        return v == rhs
    return False


def _reduce_window(values: list[float], kind: str) -> float | None:
    """Reduce a list of canonicalised values to a single aggregate."""
    if not values:
        return None
    if kind == "mean":
        return sum(values) / len(values)
    if kind == "min":
        return min(values)
    if kind == "max":
        return max(values)
    if kind == "median":
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2 == 1:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0
    return None


def _intervals_satisfy(
    chronological_readings: list[_Reading],
    interval_min_days: int,
    interval_max_days: int | None,
) -> bool:
    """Return True when every adjacent pair sits inside the interval band."""
    for i in range(1, len(chronological_readings)):
        gap_days = (
            chronological_readings[i].observed_at
            - chronological_readings[i - 1].observed_at
        ).total_seconds() / 86400.0
        if gap_days < interval_min_days:
            return False
        if interval_max_days is not None and gap_days > interval_max_days:
            return False
    return True
