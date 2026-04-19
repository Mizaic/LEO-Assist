"""Pure-function rollup helpers for the episode-engine writer.

Split out of writer.py to keep that module under the 500-LOC cap and to
make these helpers independently unit-testable. Nothing in here touches
Neo4j; everything here is deterministic in/out.
"""

from __future__ import annotations

import json
from datetime import date as _date_t
from typing import Any, Iterable

from services.analysis_worker.app.episode_engine.schemas import (
    Disruption,
    Milestone,
    SafetyNetting,
)


# -- Milestone date pickers -----------------------------------------------


def first_seen_date(ms: Iterable[Milestone]) -> str | None:
    for m in ms:
        if m.type == "first_seen":
            return m.date.isoformat()
    return None


def first_presentation(
    ms: Iterable[Milestone],
) -> tuple[str | None, str | None]:
    """Return (date_iso, presentation_place) for the earliest first_presentation."""

    candidates = [m for m in ms if m.type == "first_presentation"]
    if not candidates:
        return None, None
    chosen = min(candidates, key=lambda m: m.date)
    return chosen.date.isoformat(), chosen.presentation_place


def outcome_letter_date(ms: Iterable[Milestone]) -> str | None:
    candidates = [m for m in ms if m.type == "outcome_letter"]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda m: m.date)
    return chosen.date.isoformat()


def earliest_milestone_date(
    ms: Iterable[Milestone], milestone_type: str
) -> str | None:
    """Return the EARLIEST date for a given milestone type (ISO) or None."""

    candidates = [m for m in ms if m.type == milestone_type]
    if not candidates:
        return None
    return min(candidates, key=lambda m: m.date).date.isoformat()


# -- Disruption phase classification --------------------------------------


def _parse_iso(d: str | None) -> _date_t | None:
    if not d:
        return None
    try:
        return _date_t.fromisoformat(d)
    except ValueError:
        return None


def disruption_phase(
    disruption_date: _date_t,
    *,
    first_presentation_iso: str | None,
    referral_iso: str | None,
) -> str:
    """Bucket a disruption into NCDA avoidable-delay phases.

    Buckets:
      - before_presentation : strictly before first_presentation
      - pres_to_referral    : between first_presentation (inclusive) and
                              referral (exclusive)
      - after_referral      : on or after referral, OR no first_presentation
                              available (default for any disruption that
                              cannot be cleanly bucketed earlier)
    """

    fp = _parse_iso(first_presentation_iso)
    ref = _parse_iso(referral_iso)

    if fp and disruption_date < fp:
        return "before_presentation"
    if ref and disruption_date < ref:
        return "pres_to_referral"
    return "after_referral"


def earliest_phase(phases: list[str]) -> str | None:
    """Pick the earliest phase that has at least one disruption.

    Order: before_presentation > pres_to_referral > after_referral.
    Returns None if the list is empty.
    """

    if not phases:
        return None
    order = ("before_presentation", "pres_to_referral", "after_referral")
    for phase in order:
        if phase in phases:
            return phase
    return None


# -- Safety-netting + disruption rollup -----------------------------------


_REFERRAL_DISRUPTION_CATEGORIES = (
    "referral_lost_or_not_received",
    "referral_rejected_or_returned",
    "repeat_referral_required",
)


def safety_netting_payload(sn: SafetyNetting | None) -> dict[str, Any]:
    """Flatten a SafetyNetting into the bag of params the writer needs."""

    if sn is None or not sn.recorded:
        return {
            "safety_netting_recorded": False,
            "safety_netting_evidence": None,
            "safety_netting_encounter_id": None,
            "safety_netting_date": None,
            "safety_netting_confidence": 0.0,
        }
    return {
        "safety_netting_recorded": True,
        "safety_netting_evidence": sn.evidence_quote,
        "safety_netting_encounter_id": sn.encounter_id,
        "safety_netting_date": sn.date.isoformat() if sn.date else None,
        "safety_netting_confidence": float(sn.confidence),
    }


def disruption_summary(
    disruptions: list[Disruption],
    *,
    first_presentation_iso: str | None,
    referral_iso: str | None,
) -> dict[str, Any]:
    """Roll disruptions up into the scalars the dashboard tile reads.

    Returns a dict containing both the rollup fields and a
    ``per_disruption`` list of payloads ready for the per-link writer
    (each enriched with the resolved phase).
    """

    per: list[dict[str, Any]] = []
    phases: list[str] = []
    categories: list[str] = []
    has_referral_disruption = False

    for d in disruptions:
        phase = disruption_phase(
            d.date,
            first_presentation_iso=first_presentation_iso,
            referral_iso=referral_iso,
        )
        phases.append(phase)
        categories.append(d.category)
        if d.category in _REFERRAL_DISRUPTION_CATEGORIES:
            has_referral_disruption = True
        per.append(
            {
                "date": d.date.isoformat(),
                "category": d.category,
                "phase": phase,
                "description": d.description,
                "encounter_id": d.encounter_id,
                "evidence_quote": d.evidence_quote,
                "confidence": float(d.confidence),
            }
        )

    has_delay = bool(disruptions)
    return {
        "disruption_count": len(disruptions),
        "disruption_categories": sorted(set(categories)),
        "has_referral_disruption": has_referral_disruption,
        "avoidable_delay": has_delay,
        "avoidable_delay_phase": earliest_phase(phases) if has_delay else None,
        "disruptions_json": json.dumps(per, default=str),
        "per_disruption": per,
    }
