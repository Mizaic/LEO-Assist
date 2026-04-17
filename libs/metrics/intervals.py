"""NCDA interval KPI math.

Pure functions with no Neo4j or LLM dependency so the same values are
computed identically by:
  - services/analysis_worker/app/analyzers/kpi_calculator.py
  - scripts/build_ncda_export.py
  - any future analytics consumer.

See DI-LEO-AI-125, DO-LEO-AI-125, R-LEO-AI-085, VT-LEO-AI-120.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

# Milestone aliases accepted by compute_interval_kpis.
# Legacy single-word keys ("diagnosis", "treatment") are retained so the
# ground-truth export format and older tests continue to work.
_DIAGNOSIS_KEYS: tuple[str, ...] = ("diagnosis_confirmed", "diagnosis_date", "diagnosis")
_TREATMENT_KEYS: tuple[str, ...] = ("treatment_started", "treatment")
_REFERRAL_KEYS: tuple[str, ...] = ("referral", "referral_date")
_PRESENTATION_KEYS: tuple[str, ...] = ("first_presentation", "presentation_date")

INTERVAL_METRIC_NAMES: tuple[str, ...] = (
    "days_presentation_to_referral",
    "days_referral_to_diagnosis",
    "days_diagnosis_to_treatment",
)


def days_between(start_date: Any, end_date: Any) -> int | None:
    """Return the signed day difference between two ISO-8601 dates.

    Returns None if either argument is missing or not parseable. Accepts
    date objects or strings; anything else is coerced via str() first.
    """
    parsed_start = _coerce_date(start_date)
    parsed_end = _coerce_date(end_date)
    if parsed_start is None or parsed_end is None:
        return None
    return (parsed_end - parsed_start).days


def pick_earliest_milestone(
    milestones: dict[str, Any],
    keys: Iterable[str],
) -> str | None:
    """Return the earliest non-empty date across a set of equivalent keys.

    Useful when the same clinical milestone is stored under several key
    aliases (e.g. "diagnosis" vs "diagnosis_confirmed"). Returns the raw
    ISO-8601 string so callers can pass it straight back into
    days_between without losing precision.
    """
    valid: list[str] = []
    for key in keys:
        raw = milestones.get(key)
        if raw is None:
            continue
        parsed = _coerce_date(raw)
        if parsed is None:
            continue
        valid.append(parsed.isoformat())
    return min(valid) if valid else None


def compute_interval_kpis(milestones: dict[str, Any]) -> dict[str, int]:
    """Return the NCDA interval KPIs from a milestone dict.

    Only emits metrics whose two anchor dates are present and parseable.
    Keys in the input are looked up via canonical aliases (see
    _DIAGNOSIS_KEYS etc.) so callers can pass either the runtime
    milestone shape ("diagnosis_confirmed") or the ground-truth shape
    ("diagnosis_date").
    """
    presentation = pick_earliest_milestone(milestones, _PRESENTATION_KEYS)
    referral = pick_earliest_milestone(milestones, _REFERRAL_KEYS)
    diagnosis = pick_earliest_milestone(milestones, _DIAGNOSIS_KEYS)
    treatment = pick_earliest_milestone(milestones, _TREATMENT_KEYS)

    out: dict[str, int] = {}
    _emit_if_valid(out, "days_presentation_to_referral", presentation, referral)
    _emit_if_valid(out, "days_referral_to_diagnosis", referral, diagnosis)
    _emit_if_valid(out, "days_diagnosis_to_treatment", diagnosis, treatment)
    return out


def _emit_if_valid(
    out: dict[str, int],
    name: str,
    start: str | None,
    end: str | None,
) -> None:
    if start is None or end is None:
        return
    delta = days_between(start, end)
    if delta is None:
        return
    out[name] = delta


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Accept full datetimes by truncating to the date component.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
