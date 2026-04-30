"""Site-aware simple linker — the core NCDA scenario.

Implements the surgical first-pass rule:

    For each FTR encounter, look for a Dx encounter of the **same cancer site**
    within a configurable window (default 180 days).  If exactly one candidate
    exists, link them with high confidence.  Attach the nearest Seen-In (same
    site, between FTR and Dx) and the first Treatment (within 180 days of Dx,
    same site).

This handles Cohort 1 (FTR + Dx) cleanly and without the ML linkage classifier,
so it can be validated independently before tackling the harder multi-FTR and
historical-referral scenarios.

Output
------
Each call to ``link_patient`` returns a list of ``SimplePathway`` objects, one
per successfully linked FTR-Dx pair.  Unmatched FTRs are returned as Cohort 2,
unmatched Dx encounters are returned as Cohort 3.

Cohort assignment
-----------------
  1a  FTR + Dx (cancer_found)
  1b  FTR + Dx (cancer_excluded)
  2   FTR, no Dx within window
  3   Dx (cancer_found), no FTR within window
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Sequence

from libs.domains.read_code_ncda_lookup import (
    CancerSite,
    FTR_CODE_TO_SITE,
    SEEN_CODE_TO_SITE,
    site_from_read_codes,
    site_from_text,
)

CohortLabel = Literal["1a", "1b", "2", "3"]

_READ_CODE_RE = re.compile(r"\(([A-Za-z0-9.]+)\)")
_BREAST_IMAGING_RE = re.compile(
    r"\b(?:us scan of breast|breast ultrasound|mammogram|mammography|ultrasound scan)\b",
    re.IGNORECASE,
)
_DERMOSCOPY_RE = re.compile(r"\bdermoscop(?:y|ic)\b", re.IGNORECASE)

LINK_WINDOW_DAYS: int = 180
TREATMENT_WINDOW_DAYS: int = 180

# Two FTR encounters within this many days of each other AND with compatible
# sites are treated as the same real-world FTR submission entered twice (e.g.
# clinician starts the PRISM 2WW questionnaire at 16:35 and the secretary
# finalises it at 16:55 producing two encounters with the same date but only
# the second one carries the explicit XaMeJ Read code).  Without this
# collapse the simple linker would build TWO separate pathways and the
# detector would persist two duplicate EpisodeOfCare nodes.
NEAR_FTR_COLLAPSE_DAYS: int = 1


@dataclass(frozen=True)
class EncounterRow:
    """Minimal encounter representation for the simple linker."""

    encounter_id: str
    encounter_date: str          # ISO-8601 date string
    role: str                    # ftr / seen / dx / treatment / none
    outcome: str | None          # cancer_found / cancer_excluded / None
    text: str | None
    site: CancerSite | None = None


@dataclass
class SimplePathway:
    """A single linked NCDA pathway for one patient."""

    patient_id: str
    cohort: CohortLabel
    ftr: EncounterRow | None = None
    ftr_site: CancerSite | None = None
    seen: EncounterRow | None = None
    dx: EncounterRow | None = None
    treatment: EncounterRow | None = None
    gap_ftr_dx_days: int | None = None
    gap_ftr_seen_days: int | None = None
    gap_dx_treatment_days: int | None = None
    confidence: float = 1.0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _gap(a: str | None, b: str | None) -> int | None:
    da, db = _to_date(a), _to_date(b)
    if da is None or db is None:
        return None
    return (db - da).days


def _annotate_site(enc: EncounterRow) -> EncounterRow:
    """Return a copy of ``enc`` with ``site`` populated from its text."""
    if enc.site is not None:
        return enc
    site = site_from_read_codes(enc.text or "")
    if site is None:
        site = site_from_text(enc.text or "")
    if site is enc.site:
        return enc
    return EncounterRow(
        encounter_id=enc.encounter_id,
        encounter_date=enc.encounter_date,
        role=enc.role,
        outcome=enc.outcome,
        text=enc.text,
        site=site,
    )


def _sites_compatible(a: CancerSite | None, b: CancerSite | None) -> bool:
    """True when both sites are the same, or when either is NSS / unknown.

    The previous version allowed any haematological malignancy to wildcard-
    match every FTR site, on the rationale that lymphoma can be discovered
    incidentally on a breast or head-and-neck 2WW.  In practice that
    wildcard caused FPs (e.g. patient 6310920987: breast-screening FTR
    silently linked to a CLL dx 39 days later, producing a phantom cohort-1a
    breast episode).  Genuine "incidental haematological discovery on a
    site-specific 2WW" still falls into cohort 3 where the dx encounter has
    no FTR within window — that is the correct NCDA route classification.
    """
    if a is None or b is None:
        return True
    if a == "nss" or b == "nss":
        return True
    return a == b


def _ftr_sites_compatible_for_collapse(
    a: CancerSite | None, b: CancerSite | None
) -> bool:
    """Stricter site-compatibility for collapsing duplicate FTR submissions.

    Unlike ``_sites_compatible`` (which is used to link FTRs to Dx and so
    treats haematological / NSS as wildcards), this only treats two FTRs as
    duplicates when they have the SAME site, or when at least one site is
    unknown (``None``).  We deliberately do NOT collapse a haematological FTR
    with a same-day breast FTR — those are clinically distinct submissions
    even if hard-to-distinguish at the linker stage.
    """
    if a is None or b is None:
        return True
    return a == b


def _ftr_specificity(enc: EncounterRow) -> int:
    """Return a sortable canonicality score for an FTR.

    Higher is more canonical.  Used to pick the surviving FTR when a cluster
    of near-duplicate same-day FTRs is collapsed.

    Heuristics:
        +3  encounter has an explicit FTR Read code in its text (XaMeJ etc.)
        +2  encounter has a non-None inferred site (text mentions e.g. 'lung')
        +1  encounter has any text at all (vs. a stub row)
    """
    score = 0
    text = enc.text or ""
    if any(code in text for code in FTR_CODE_TO_SITE):
        score += 3
    if enc.site is not None:
        score += 2
    if text.strip():
        score += 1
    return score


def _collapse_near_duplicate_ftrs(
    ftrs: Sequence[EncounterRow],
    *,
    window_days: int,
) -> tuple[list[EncounterRow], list[tuple[EncounterRow, EncounterRow]]]:
    """Collapse FTRs that look like the same real-world submission entered twice.

    Two FTRs are considered duplicates when:
        - They are within ``window_days`` days of each other; AND
        - Their sites are compatible (``_sites_compatible``), i.e. same site
          or one of them has no inferred site at all.

    The most canonical FTR in each cluster (per ``_ftr_specificity``) is kept.
    Ties broken by latest ``encounter_date`` (the finalised submission usually
    follows the started one).

    Returns:
        (kept, dropped_pairs) where ``dropped_pairs`` is a list of
        ``(dropped_ftr, kept_ftr)`` so the caller can log/audit which
        encounters were collapsed.
    """
    if window_days < 0:
        return list(ftrs), []
    sorted_ftrs = sorted(
        ftrs,
        key=lambda e: (e.encounter_date or "", e.encounter_id),
    )
    kept: list[EncounterRow] = []
    dropped: list[tuple[EncounterRow, EncounterRow]] = []
    for cand in sorted_ftrs:
        cand_date = _to_date(cand.encounter_date)
        merged_with: EncounterRow | None = None
        for i, existing in enumerate(kept):
            existing_date = _to_date(existing.encounter_date)
            if cand_date is None or existing_date is None:
                continue
            if abs((cand_date - existing_date).days) > window_days:
                continue
            if not _ftr_sites_compatible_for_collapse(existing.site, cand.site):
                continue
            cand_score = _ftr_specificity(cand)
            existing_score = _ftr_specificity(existing)
            if (
                cand_score > existing_score
                or (
                    cand_score == existing_score
                    and (cand.encounter_date or "") > (existing.encounter_date or "")
                )
            ):
                kept[i] = cand
                dropped.append((existing, cand))
            else:
                dropped.append((cand, existing))
            merged_with = cand
            break
        if merged_with is None:
            kept.append(cand)
    return kept, dropped


def _more_specific_ftr_exists(
    ftr: EncounterRow,
    dx: EncounterRow,
    ftrs: Sequence[EncounterRow],
) -> bool:
    """True when an unknown-site FTR should defer to a later same-site FTR."""
    if ftr.site is not None or dx.site is None:
        return False
    ftr_date = _to_date(ftr.encounter_date)
    dx_date = _to_date(dx.encounter_date)
    if ftr_date is None or dx_date is None:
        return False
    for other in ftrs:
        if other.encounter_id == ftr.encounter_id:
            continue
        other_date = _to_date(other.encounter_date)
        if other_date is None:
            continue
        if other.site == dx.site and ftr_date < other_date <= dx_date:
            return True
    return False


def _close_silent_assessment(
    dx: EncounterRow,
    *,
    dxs: Sequence[EncounterRow],
    treatments: Sequence[EncounterRow],
    latest_encounter_date: date | None,
    silence_window_days: int,
) -> EncounterRow:
    """Treat low-risk assessments as cancer-excluded after 180d of silence."""
    dx_date = _to_date(dx.encounter_date)
    is_silent_breast_imaging = dx.site == "breast" and bool(
        _BREAST_IMAGING_RE.search(dx.text or "")
    )
    is_silent_dermoscopy = dx.site == "skin" and bool(
        _DERMOSCOPY_RE.search(dx.text or "")
    )
    if (
        dx.outcome is not None
        or dx_date is None
        or latest_encounter_date is None
        or latest_encounter_date < dx_date + timedelta(days=silence_window_days)
        or not (is_silent_breast_imaging or is_silent_dermoscopy)
    ):
        return dx

    for later_dx in dxs:
        later_date = _to_date(later_dx.encounter_date)
        if later_date is None or later_date <= dx_date:
            continue
        if (later_date - dx_date).days > silence_window_days:
            continue
        if _sites_compatible(dx.site, later_dx.site) and later_dx.outcome is not None:
            return dx

    for treatment in treatments:
        treatment_date = _to_date(treatment.encounter_date)
        if treatment_date is None or treatment_date <= dx_date:
            continue
        if (treatment_date - dx_date).days > silence_window_days:
            continue
        if _sites_compatible(dx.site, treatment.site):
            return dx

    return EncounterRow(
        encounter_id=dx.encounter_id,
        encounter_date=dx.encounter_date,
        role=dx.role,
        outcome="cancer_excluded",
        text=dx.text,
        site=dx.site,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def annotate_sites(encounters: Sequence[EncounterRow]) -> list[EncounterRow]:
    """Return encounters with ``site`` populated from Read codes or keywords."""
    return [_annotate_site(e) for e in encounters]


def link_patient(
    patient_id: str,
    encounters: Sequence[EncounterRow],
    *,
    link_window_days: int = LINK_WINDOW_DAYS,
    treatment_window_days: int = TREATMENT_WINDOW_DAYS,
    near_ftr_collapse_days: int = NEAR_FTR_COLLAPSE_DAYS,
) -> list[SimplePathway]:
    """Build NCDA pathways for one patient using the site-aware simple linker.

    Args:
        patient_id: Patient NHS number or graph ID (for output only).
        encounters: All role-scored encounters for this patient, in any order.
        link_window_days: Maximum FTR-to-Dx gap to be considered the same
            pathway.  Default 180 days (six months).
        treatment_window_days: Maximum Dx-to-Treatment gap to attach a
            treatment anchor.  Default 180 days.

    Returns:
        A list of ``SimplePathway`` objects.  Cohort 1 pathways are one per
        linked FTR-Dx pair.  Unmatched FTRs become Cohort 2; unmatched cancer-
        found Dx encounters become Cohort 3.
    """
    # Annotate sites for all encounters
    encs = annotate_sites(encounters)

    # Partition by role
    ftrs = sorted(
        [e for e in encs if e.role == "ftr"],
        key=lambda e: e.encounter_date or "",
    )
    # Collapse near-duplicate FTRs (e.g. PRISM 2WW questionnaire started by
    # one staff member and finalised by another, within the same day).
    ftrs, _collapsed_pairs = _collapse_near_duplicate_ftrs(
        ftrs, window_days=near_ftr_collapse_days
    )
    seens = sorted(
        [e for e in encs if e.role == "seen"],
        key=lambda e: e.encounter_date or "",
    )
    dxs = sorted(
        [e for e in encs if e.role == "dx"],
        key=lambda e: e.encounter_date or "",
    )
    treatments = sorted(
        [e for e in encs if e.role == "treatment"],
        key=lambda e: e.encounter_date or "",
    )
    encounter_dates = [d for d in (_to_date(e.encounter_date) for e in encs) if d is not None]
    latest_encounter_date = max(encounter_dates, default=None)

    pathways: list[SimplePathway] = []
    used_ftr_ids: set[str] = set()
    used_dx_ids: set[str] = set()

    # --- Cohort 1: FTR + Dx (same site, within window) ---
    for ftr in ftrs:
        ftr_date = _to_date(ftr.encounter_date)
        if ftr_date is None:
            continue

        # Step 1: find the nearest Seen-In within the window so we can anchor
        # Dx selection to after the first specialist appointment.
        seen_in: EncounterRow | None = None
        gap_fs: int | None = None
        candidates_seen = [
            s for s in seens
            if _sites_compatible(ftr.site, s.site)
            and (ftr.site is None or s.site is not None)
            and _to_date(s.encounter_date) is not None
            and 0 < (_to_date(s.encounter_date) - ftr_date).days <= link_window_days  # type: ignore[operator]
        ]
        if candidates_seen:
            seen_in = min(candidates_seen, key=lambda s: s.encounter_date or "")
            gap_fs = _gap(ftr.encounter_date, seen_in.encounter_date)

        # Step 2: pick the earliest Dx encounter in the pathway.  Prefer the FTR
        # window, but allow longer pathways when a Seen-In anchor falls between
        # the FTR and Dx (e.g. Seen-In at day 29, Dx at day 182).  Do not require
        # Dx to occur after Seen-In: imported clinic letters often record the
        # investigation/result as the outcome without a separate clean Seen-In.
        candidates = [
            dx for dx in dxs
            if dx.encounter_id not in used_dx_ids
            and _sites_compatible(ftr.site, dx.site)
            and not _more_specific_ftr_exists(ftr, dx, ftrs)
            and _to_date(dx.encounter_date) is not None
            and (
                0 <= (_to_date(dx.encounter_date) - ftr_date).days <= link_window_days  # type: ignore[operator]
                or any(
                    _to_date(s.encounter_date) is not None
                    and _to_date(s.encounter_date) <= _to_date(dx.encounter_date)  # type: ignore[operator]
                    and 0 <= (_to_date(dx.encounter_date) - _to_date(s.encounter_date)).days <= link_window_days  # type: ignore[union-attr,operator]
                    for s in candidates_seen
                )
            )
        ]

        if not candidates:
            continue

        # Prefer candidates with an explicit outcome (cancer_found / cancer_excluded)
        # over those where outcome is None (interim clinic letters, phlebotomy visits,
        # imaging results that triggered the dx phrase matcher incidentally).
        # Among the preferred set, pick the earliest: the first formal outcome
        # determination is the correct NCDA milestone date.
        outcome_candidates = [c for c in candidates if c.outcome is not None]
        pool = outcome_candidates if outcome_candidates else candidates
        dx = min(pool, key=lambda d: d.encounter_date or "")
        dx = _close_silent_assessment(
            dx,
            dxs=dxs,
            treatments=treatments,
            latest_encounter_date=latest_encounter_date,
            silence_window_days=link_window_days,
        )
        gap_fd = _gap(ftr.encounter_date, dx.encounter_date)

        dx_date = _to_date(dx.encounter_date)

        # Refine Seen-In: constrain to between FTR and the chosen Dx
        if candidates_seen:
            candidates_seen_refined = [
                s for s in candidates_seen
                if dx_date is None or _to_date(s.encounter_date) <= dx_date  # type: ignore[operator]
            ]
            if candidates_seen_refined:
                seen_in = min(candidates_seen_refined, key=lambda s: s.encounter_date or "")
                gap_fs = _gap(ftr.encounter_date, seen_in.encounter_date)
            else:
                seen_in = None
                gap_fs = None

        # First Treatment after Dx, same site
        tx: EncounterRow | None = None
        gap_dt: int | None = None
        if dx.outcome == "cancer_found" and dx_date:
            candidates_tx = [
                t for t in treatments
                if _to_date(t.encounter_date) is not None
                and 0 <= (_to_date(t.encounter_date) - dx_date).days <= treatment_window_days  # type: ignore[operator]
            ]
            if candidates_tx:
                tx = min(candidates_tx, key=lambda t: t.encounter_date or "")
                gap_dt = _gap(dx.encounter_date, tx.encounter_date)

        cohort: CohortLabel = "1a" if dx.outcome == "cancer_found" else "1b"

        pathways.append(
            SimplePathway(
                patient_id=patient_id,
                cohort=cohort,
                ftr=ftr,
                ftr_site=ftr.site,
                seen=seen_in,
                dx=dx,
                treatment=tx,
                gap_ftr_dx_days=gap_fd,
                gap_ftr_seen_days=gap_fs,
                gap_dx_treatment_days=gap_dt,
                confidence=1.0,
                notes=[f"Simple same-site linker: {ftr.site} within {gap_fd}d"],
            )
        )

        used_ftr_ids.add(ftr.encounter_id)
        used_dx_ids.add(dx.encounter_id)

    # --- Cohort 2: FTR with no Dx linked ---
    for ftr in ftrs:
        if ftr.encounter_id in used_ftr_ids:
            continue
        pathways.append(
            SimplePathway(
                patient_id=patient_id,
                cohort="2",
                ftr=ftr,
                ftr_site=ftr.site,
                confidence=0.8,
                notes=["No Dx encounter found within window for this FTR"],
            )
        )

    # --- Cohort 3: Cancer-found Dx with no FTR linked ---
    for dx in dxs:
        if dx.encounter_id in used_dx_ids:
            continue
        if dx.outcome != "cancer_found":
            continue  # cancer_excluded without FTR is not clinically notable

        # First Treatment after this Dx
        tx = None
        gap_dt = None
        dx_date = _to_date(dx.encounter_date)
        if dx_date:
            candidates_tx = [
                t for t in treatments
                if _to_date(t.encounter_date) is not None
                and 0 <= (_to_date(t.encounter_date) - dx_date).days <= treatment_window_days  # type: ignore[operator]
            ]
            if candidates_tx:
                tx = min(candidates_tx, key=lambda t: t.encounter_date or "")
                gap_dt = _gap(dx.encounter_date, tx.encounter_date)

        pathways.append(
            SimplePathway(
                patient_id=patient_id,
                cohort="3",
                dx=dx,
                treatment=tx,
                gap_dx_treatment_days=gap_dt,
                confidence=0.9,
                notes=["Cancer-found Dx with no FTR within window"],
            )
        )

    return pathways
