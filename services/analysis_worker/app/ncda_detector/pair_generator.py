"""Stage 5 - Candidate (FTR, Dx) pair generator.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Consumes role-classifier outputs and emits candidate pairs for the linkage
classifier (Stage 6). Auxiliary anchors (SEEN, TREATMENT) travel through
as a per-patient table; they are attached deterministically by Stage 7.

Anchor selection:
  - FTR candidate: any encounter with role_probabilities['ftr'] >= ftr_threshold.
  - Dx candidate: any encounter with role_probabilities['dx'] >= dx_threshold.
  - SEEN aux: role_probabilities['seen'] >= seen_threshold.
  - TREATMENT aux: role_probabilities['treatment'] >= treatment_threshold.

Pair window:
  Default [-90d, +365d] from Dx; configurable via ``window``.
  Singletons emitted when an FTR has no Dx in window (cohort 2 input)
  or a Dx with outcome=cancer_found has no FTR in window (cohort 3 input).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RoleScore:
    """One encounter's role-classifier output, plus its raw text/date."""

    encounter_id: str
    encounter_date: str
    role_probabilities: dict[str, float]
    outcome: str | None
    outcome_probability: float | None
    text: str | None = None
    flags: str | None = None


@dataclass(frozen=True)
class CandidatePair:
    """One FTR/Dx pair (or singleton) emitted to the linkage classifier."""

    patient_id: str
    ftr_encounter_id: str | None
    dx_encounter_id: str | None
    ftr_role_p: float
    dx_role_p: float
    dx_outcome: str | None
    dx_outcome_p: float | None
    gap_days: int | None
    ftr_date: str | None
    dx_date: str | None


@dataclass(frozen=True)
class PairWindow:
    """Window for FTR -> Dx pairing in days."""

    min_gap_days: int = -90
    max_gap_days: int = 365


@dataclass(frozen=True)
class PairThresholds:
    """Per-role probability thresholds for anchor admission."""

    ftr: float = 0.5
    dx: float = 0.5
    seen: float = 0.5
    treatment: float = 0.5


@dataclass(frozen=True)
class AuxiliaryAnchors:
    """Per-patient predicted auxiliary anchors (SEEN, TREATMENT)."""

    patient_id: str
    seen: list[RoleScore]
    treatment: list[RoleScore]


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _filter_by_role(
    scores: Iterable[RoleScore], role: str, threshold: float
) -> list[RoleScore]:
    return [s for s in scores if s.role_probabilities.get(role, 0.0) >= threshold]


def generate_pairs(
    *,
    patient_id: str,
    scores: Sequence[RoleScore],
    thresholds: PairThresholds = PairThresholds(),
    window: PairWindow = PairWindow(),
) -> tuple[list[CandidatePair], AuxiliaryAnchors]:
    """Emit candidate pairs and auxiliary anchors for one patient."""
    ftrs = _filter_by_role(scores, "ftr", thresholds.ftr)
    dxs = _filter_by_role(scores, "dx", thresholds.dx)
    seens = _filter_by_role(scores, "seen", thresholds.seen)
    txs = _filter_by_role(scores, "treatment", thresholds.treatment)

    pairs = _emit_paired_combinations(patient_id, ftrs, dxs, window)
    pairs.extend(_emit_unmatched_ftr_singletons(patient_id, ftrs, dxs, window))
    pairs.extend(_emit_unmatched_dx_singletons(patient_id, ftrs, dxs, window))

    return pairs, AuxiliaryAnchors(patient_id=patient_id, seen=seens, treatment=txs)


def _emit_paired_combinations(
    patient_id: str,
    ftrs: list[RoleScore],
    dxs: list[RoleScore],
    window: PairWindow,
) -> list[CandidatePair]:
    out: list[CandidatePair] = []
    for ftr in ftrs:
        for dx in dxs:
            gap = _gap_days(ftr.encounter_date, dx.encounter_date)
            if gap is None:
                continue
            if gap < window.min_gap_days or gap > window.max_gap_days:
                continue
            out.append(_pair_record(patient_id, ftr, dx, gap))
    return out


def _emit_unmatched_ftr_singletons(
    patient_id: str,
    ftrs: list[RoleScore],
    dxs: list[RoleScore],
    window: PairWindow,
) -> list[CandidatePair]:
    out: list[CandidatePair] = []
    for ftr in ftrs:
        if any(_in_window(ftr, dx, window) for dx in dxs):
            continue
        out.append(_singleton_record(patient_id, ftr=ftr, dx=None))
    return out


def _emit_unmatched_dx_singletons(
    patient_id: str,
    ftrs: list[RoleScore],
    dxs: list[RoleScore],
    window: PairWindow,
) -> list[CandidatePair]:
    """Emit Dx-only singletons; only the cancer_found outcomes go to cohort 3.

    Cancer_excluded singletons are dropped (no QI value as a singleton).
    """
    out: list[CandidatePair] = []
    for dx in dxs:
        if dx.outcome != "cancer_found":
            continue
        if any(_in_window(ftr, dx, window) for ftr in ftrs):
            continue
        out.append(_singleton_record(patient_id, ftr=None, dx=dx))
    return out


def _in_window(
    ftr: RoleScore, dx: RoleScore, window: PairWindow
) -> bool:
    gap = _gap_days(ftr.encounter_date, dx.encounter_date)
    return gap is not None and window.min_gap_days <= gap <= window.max_gap_days


def _gap_days(ftr_date: str, dx_date: str) -> int | None:
    a = _to_date(ftr_date)
    b = _to_date(dx_date)
    if a is None or b is None:
        return None
    return (b - a).days


def _pair_record(
    patient_id: str, ftr: RoleScore, dx: RoleScore, gap: int
) -> CandidatePair:
    return CandidatePair(
        patient_id=patient_id,
        ftr_encounter_id=ftr.encounter_id,
        dx_encounter_id=dx.encounter_id,
        ftr_role_p=ftr.role_probabilities.get("ftr", 0.0),
        dx_role_p=dx.role_probabilities.get("dx", 0.0),
        dx_outcome=dx.outcome,
        dx_outcome_p=dx.outcome_probability,
        gap_days=gap,
        ftr_date=ftr.encounter_date,
        dx_date=dx.encounter_date,
    )


def _singleton_record(
    patient_id: str,
    *,
    ftr: RoleScore | None,
    dx: RoleScore | None,
) -> CandidatePair:
    return CandidatePair(
        patient_id=patient_id,
        ftr_encounter_id=ftr.encounter_id if ftr else None,
        dx_encounter_id=dx.encounter_id if dx else None,
        ftr_role_p=ftr.role_probabilities.get("ftr", 0.0) if ftr else 0.0,
        dx_role_p=dx.role_probabilities.get("dx", 0.0) if dx else 0.0,
        dx_outcome=dx.outcome if dx else None,
        dx_outcome_p=dx.outcome_probability if dx else None,
        gap_days=None,
        ftr_date=ftr.encounter_date if ftr else None,
        dx_date=dx.encounter_date if dx else None,
    )
