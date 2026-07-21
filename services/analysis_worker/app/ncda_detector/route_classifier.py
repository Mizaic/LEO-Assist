"""Deterministic place-of-presentation / diagnosis-route labels for NCDA pathways.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Uses the same inputs as inference (text + Read codes + roles).  No ML.

These routes explain *how* the patient reached diagnosis relative to primary-care
fast-track referral, not the anchor roles themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

from services.analysis_worker.app.ncda_detector.audit_rules import extract_read_codes
from services.analysis_worker.app.ncda_detector.simple_linker import (
    EncounterRow,
    SimplePathway,
)

NcdaDiagnosisRoute = Literal[
    "gp_surgery_fast_track",
    "screening",
    "emergency_or_urgent_care",
    "routine_gp_investigation",
    "specialist_surveillance_incidental",
    "secondary_care_surgical",
    "fast_track_clinic_referral_missing",
    "external_or_unknown_route",
    "unknown",
]

# Emergency text only counts when seen close to the Dx date (cohort 3 only).
# 90 days is generous enough for late-coding while excluding unrelated old A&E
# attendances (e.g. childhood asthma admission years before a cancer diagnosis).
_EMERGENCY_PROXIMITY_DAYS = 90

_SCREENING_READ_CODES = frozenset({"68621", "XaPVj"})
_SCREENING_PHRASE = re.compile(
    r"\b(Bowel Cancer Screening|FOBT Abnormal|FIT Positive)\b",
    re.IGNORECASE,
)
_EMERGENCY_RE = re.compile(
    r"\b(A&E|AE department|accident and emergency|emergency department"
    r"|ED attendance|\bED\b"
    r"|999\s+call|called\s+999|ambulance"
    r"|urgent treatment centre|\bUTC\b"
    r"|walk[- ]in centre|minor injuries unit|\bMIU\b"
    r"|Emergency admission|admitted.*(?:A&E|emergency))\b",
    re.IGNORECASE,
)
_SURVEILLANCE_RE = re.compile(
    r"\b(surveillance colonoscopy|surveillance endoscopy"
    r"|routine surveillance"
    r"|PSA monitoring|annual urology (?:review|follow)"
    r"|under surveillance for)\b",
    re.IGNORECASE,
)
_SURGERY_BEFORE_DX_RE = re.compile(
    r"\b(?:underwent|had (?:an |a )?)(?:open |lap(?:aro)?scopic )?"
    r"(colectomy|hemicolectomy|mastectomy|nephrectomy|oesophagectomy"
    r"|pneumonectomy|prostatectomy|thyroidectomy|whipple)"
    r"|(?:excision|resection) of (?:the )?(?:tumou?r|mass|lesion)",
    re.IGNORECASE,
)
_FT_SEEN_NO_GP_RE = re.compile(
    r"\b(?:Seen in|Attended).*(?:2\s*WW|two\s*week\s*wait"
    r"|fast\s*track\s*suspected\s*cancer)",
    re.IGNORECASE,
)
_ROUTINE_REFERRAL_RE = re.compile(
    r"\b(?:routine (?:referral|endoscopy)|referral to (?:routine|non[- ]urgent)"
    r"|IDA (?:work[- ]?up|investigation))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteClassification:
    """Diagnosis route plus short audit rationale."""

    route: NcdaDiagnosisRoute
    rationale: tuple[str, ...]


def _parse_iso(d: str | None) -> tuple[int, int, int] | None:
    if not d:
        return None
    s = str(d)[:10]
    parts = s.split("-")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _date_before(a: str | None, b: str | None) -> bool:
    """True iff date strings compare as *strictly before* (yyyy-mm-dd)."""
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None or db is None:
        return False
    return da < db


def _days_between(a: str | None, b: str | None) -> int | None:
    """Absolute days between two yyyy-mm-dd strings, or None on parse failure."""
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None or db is None:
        return None
    from datetime import date

    return abs((date(*da) - date(*db)).days)


def _join_text_before_dx(
    labeled_encounters: Sequence[tuple[str, str, str]],
    dx_date: str | None,
) -> str:
    """Concatenate encounter text for rows strictly before the Dx date."""
    if not dx_date:
        return ""
    chunks: list[str] = []
    for enc_date, text, _role in labeled_encounters:
        if _date_before(enc_date, dx_date):
            chunks.append(text or "")
    return "\n".join(chunks)


def _join_text_window_before_dx(
    labeled_encounters: Sequence[tuple[str, str, str]],
    dx_date: str | None,
    *,
    max_days: int,
) -> str:
    """Concatenate encounter text within ``max_days`` strictly before Dx."""
    if not dx_date:
        return ""
    chunks: list[str] = []
    for enc_date, text, _role in labeled_encounters:
        if not _date_before(enc_date, dx_date):
            continue
        gap = _days_between(enc_date, dx_date)
        if gap is None or gap > max_days:
            continue
        chunks.append(text or "")
    return "\n".join(chunks)


def _join_text_on_or_before(
    labeled_encounters: Sequence[tuple[str, str, str]],
    dx_date: str | None,
) -> str:
    """Include same-day as Dx for clinic-letter alignment."""
    if not dx_date:
        return ""
    chunks: list[str] = []
    px = _parse_iso(dx_date)
    if px is None:
        return ""
    for enc_date, text, _role in labeled_encounters:
        q = _parse_iso(enc_date)
        if q is not None and q <= px:
            chunks.append(text or "")
    return "\n".join(chunks)


def _ftr_is_screening(ftr: EncounterRow | None) -> bool:
    if not ftr:
        return False
    text = ftr.text or ""
    codes = set(extract_read_codes(text))
    if codes & _SCREENING_READ_CODES:
        return True
    return bool(_SCREENING_PHRASE.search(text))


def classify_diagnosis_route(
    pathway: SimplePathway,
    *,
    labeled_encounters: Sequence[tuple[str, str, str]],
) -> RouteClassification:
    """Assign a single primary diagnosis route for one ``SimplePathway``.

    Args:
        pathway: Linked pathway from ``simple_linker.link_patient``.
        labeled_encounters: Chronological ``(encounter_date, text, role)`` rows
            for this patient (same ordering as passed to the linker).

    Returns:
        RouteClassification with one route label and terse rationale strings.
    """
    cohort = pathway.cohort
    dx = pathway.dx
    dx_date = dx.encounter_date if dx else None

    if cohort == "2":
        return RouteClassification(
            route="unknown",
            rationale=("cohort_2_no_linked_dx",),
        )

    if cohort == "3":
        return _route_cohort_three(pathway, labeled_encounters, dx_date)

    if cohort not in ("1a", "1b"):
        return RouteClassification(route="unknown", rationale=("unhandled_cohort",))

    ftr = pathway.ftr

    if _ftr_is_screening(ftr):
        return RouteClassification(
            route="screening",
            rationale=("screening_read_code_or_screening_phrase_on_ftr",),
        )

    return RouteClassification(
        route="gp_surgery_fast_track",
        rationale=("linked_ftr_and_dx_default_gp_fast_track",),
    )


def _route_cohort_three(
    pathway: SimplePathway,
    labeled_encounters: Sequence[tuple[str, str, str]],
    dx_date: str | None,
) -> RouteClassification:
    """Dx without linked FTR within window."""
    del pathway
    before_dx = _join_text_before_dx(labeled_encounters, dx_date)
    on_or_before_dx = _join_text_on_or_before(labeled_encounters, dx_date)
    near_dx = _join_text_window_before_dx(
        labeled_encounters, dx_date, max_days=_EMERGENCY_PROXIMITY_DAYS
    )

    # Emergency only counts when it appears close to the Dx, otherwise unrelated
    # historical A&E attendances drown out the actual diagnosis route.
    if near_dx and _EMERGENCY_RE.search(near_dx):
        return RouteClassification(
            route="emergency_or_urgent_care",
            rationale=("emergency_within_90_days_before_dx",),
        )

    codes_before: set[str] = set()
    for enc_date, text, _role in labeled_encounters:
        if _date_before(enc_date, dx_date):
            codes_before.update(extract_read_codes(text or ""))
    if codes_before & _SCREENING_READ_CODES or (
        before_dx and _SCREENING_PHRASE.search(before_dx)
    ):
        return RouteClassification(
            route="screening",
            rationale=("screening_evidence_before_dx_no_linked_ftr",),
        )

    if _FT_SEEN_NO_GP_RE.search(on_or_before_dx):
        return RouteClassification(
            route="fast_track_clinic_referral_missing",
            rationale=("seen_2ww_clinic_text_without_linked_gp_ftr",),
        )

    if before_dx and _SURVEILLANCE_RE.search(before_dx):
        return RouteClassification(
            route="specialist_surveillance_incidental",
            rationale=("surveillance_phrase_before_dx",),
        )

    if before_dx and _SURGERY_BEFORE_DX_RE.search(before_dx):
        return RouteClassification(
            route="secondary_care_surgical",
            rationale=("major_surgery_phrase_before_dx",),
        )

    if before_dx and _ROUTINE_REFERRAL_RE.search(before_dx):
        return RouteClassification(
            route="routine_gp_investigation",
            rationale=("routine_referral_pattern_before_dx",),
        )

    # When the GP record carries a cancer diagnosis without referral, screening,
    # surveillance, surgery or A&E evidence near the Dx, the pathway most
    # likely originated outside primary care (e.g. private referral, secondary-
    # care incidental, hospital transfer). Route attribution is unsafe to
    # guess; flag explicitly for reviewer triage.
    return RouteClassification(
        route="external_or_unknown_route",
        rationale=("cohort_3_no_clear_gp_or_emergency_evidence",),
    )
