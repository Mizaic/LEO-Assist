"""Stage 7 - Pair assignment, auxiliary attachment, cohort labelling.

Greedy max-probability matching for FTR-Dx with per-Dx uniqueness; FTR may
bind to >=1 Dx. Deterministic auxiliary attachment of nearest in-interval
SEEN and (when outcome is cancer_found) nearest post-Dx TREATMENT.

Cohorts:
  - 1a: linked, cancer_found
  - 1b: linked, cancer_excluded
  - 2: unmatched FTR (no Dx in window)
  - 3: unmatched cancer-found Dx (no FTR in window)
  - 4: multiple linked pairs / mixed for the patient
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal, Sequence

from services.analysis_worker.app.ncda_detector.linkage import LinkageScore
from services.analysis_worker.app.ncda_detector.pair_generator import (
    AuxiliaryAnchors,
    CandidatePair,
    RoleScore,
)

Cohort = Literal["1a", "1b", "2", "3", "4"]
Tier = Literal["auto", "suggest", "review"]


@dataclass(frozen=True)
class EpisodeCandidate:
    """One emitted EpisodeOfCare candidate plus its anchors and metadata."""

    patient_id: str
    cohort: Cohort
    tier: Tier
    ftr_encounter_id: str | None
    ftr_date: str | None
    seen_encounter_id: str | None
    seen_date: str | None
    dx_encounter_id: str | None
    dx_date: str | None
    dx_outcome: str | None
    treatment_encounter_id: str | None
    treatment_date: str | None
    linkage_probability: float
    sub_state: str | None = None  # for cohort 4 sub-pairs
    seen_missing: bool = False
    treatment_missing: bool = False


@dataclass
class AssignmentResult:
    """Per-patient list of EpisodeCandidates plus diagnostics."""

    patient_id: str
    candidates: list[EpisodeCandidate] = field(default_factory=list)
    skipped_pairs: int = 0
    dropped_dx_excluded_singletons: int = 0


def assign(
    patient_id: str,
    pairs_with_scores: Iterable[tuple[CandidatePair, LinkageScore]],
    aux: AuxiliaryAnchors,
) -> AssignmentResult:
    """Run the assignment pipeline for one patient."""
    sorted_pairs = sorted(
        list(pairs_with_scores), key=lambda x: x[1].probability, reverse=True
    )
    full_pairs, ftr_singletons, dx_singletons = _bucket_pairs(sorted_pairs)
    used_dx: set[str] = set()
    candidates: list[EpisodeCandidate] = []

    for pair, score in full_pairs:
        if score.tier == "review":
            continue
        if pair.dx_encounter_id in used_dx:
            continue
        used_dx.add(pair.dx_encounter_id)  # type: ignore[arg-type]
        candidates.append(_linked_candidate(patient_id, pair, score, aux))

    for pair, score in ftr_singletons:
        if pair.ftr_encounter_id and not _ftr_already_paired(
            pair.ftr_encounter_id, candidates
        ):
            candidates.append(_unmatched_ftr_candidate(patient_id, pair, aux))

    for pair, score in dx_singletons:
        if pair.dx_encounter_id and pair.dx_encounter_id not in used_dx:
            used_dx.add(pair.dx_encounter_id)
            candidates.append(_unmatched_dx_candidate(patient_id, pair, aux))

    candidates = _maybe_promote_cohort_4(candidates)
    return AssignmentResult(patient_id=patient_id, candidates=candidates)


def _bucket_pairs(
    sorted_pairs: list[tuple[CandidatePair, LinkageScore]],
):
    full: list[tuple[CandidatePair, LinkageScore]] = []
    ftr_singletons: list[tuple[CandidatePair, LinkageScore]] = []
    dx_singletons: list[tuple[CandidatePair, LinkageScore]] = []
    for pair, score in sorted_pairs:
        if pair.ftr_encounter_id and pair.dx_encounter_id:
            full.append((pair, score))
        elif pair.ftr_encounter_id:
            ftr_singletons.append((pair, score))
        else:
            dx_singletons.append((pair, score))
    return full, ftr_singletons, dx_singletons


def _ftr_already_paired(ftr_id: str, candidates: list[EpisodeCandidate]) -> bool:
    return any(c.ftr_encounter_id == ftr_id and c.dx_encounter_id for c in candidates)


def _linked_candidate(
    patient_id: str,
    pair: CandidatePair,
    score: LinkageScore,
    aux: AuxiliaryAnchors,
) -> EpisodeCandidate:
    seen, seen_missing = _attach_seen_in_window(pair, aux.seen, "linked")
    treatment, tx_missing = _attach_treatment(pair, aux.treatment)
    cohort: Cohort = "1a" if pair.dx_outcome == "cancer_found" else "1b"
    return EpisodeCandidate(
        patient_id=patient_id,
        cohort=cohort,
        tier=score.tier,
        ftr_encounter_id=pair.ftr_encounter_id,
        ftr_date=pair.ftr_date,
        seen_encounter_id=seen.encounter_id if seen else None,
        seen_date=seen.encounter_date if seen else None,
        dx_encounter_id=pair.dx_encounter_id,
        dx_date=pair.dx_date,
        dx_outcome=pair.dx_outcome,
        treatment_encounter_id=treatment.encounter_id if treatment else None,
        treatment_date=treatment.encounter_date if treatment else None,
        linkage_probability=score.probability,
        seen_missing=seen_missing,
        treatment_missing=tx_missing,
    )


def _unmatched_ftr_candidate(
    patient_id: str,
    pair: CandidatePair,
    aux: AuxiliaryAnchors,
) -> EpisodeCandidate:
    seen, seen_missing = _attach_seen_in_window(pair, aux.seen, "unmatched_ftr")
    return EpisodeCandidate(
        patient_id=patient_id,
        cohort="2",
        tier="review",
        ftr_encounter_id=pair.ftr_encounter_id,
        ftr_date=pair.ftr_date,
        seen_encounter_id=seen.encounter_id if seen else None,
        seen_date=seen.encounter_date if seen else None,
        dx_encounter_id=None,
        dx_date=None,
        dx_outcome=None,
        treatment_encounter_id=None,
        treatment_date=None,
        linkage_probability=0.0,
        seen_missing=seen_missing,
        treatment_missing=True,
    )


def _unmatched_dx_candidate(
    patient_id: str,
    pair: CandidatePair,
    aux: AuxiliaryAnchors,
) -> EpisodeCandidate:
    seen, seen_missing = _attach_seen_in_window(pair, aux.seen, "unmatched_dx")
    treatment, tx_missing = _attach_treatment(pair, aux.treatment)
    return EpisodeCandidate(
        patient_id=patient_id,
        cohort="3",
        tier="review",
        ftr_encounter_id=None,
        ftr_date=None,
        seen_encounter_id=seen.encounter_id if seen else None,
        seen_date=seen.encounter_date if seen else None,
        dx_encounter_id=pair.dx_encounter_id,
        dx_date=pair.dx_date,
        dx_outcome=pair.dx_outcome,
        treatment_encounter_id=treatment.encounter_id if treatment else None,
        treatment_date=treatment.encounter_date if treatment else None,
        linkage_probability=0.0,
        seen_missing=seen_missing,
        treatment_missing=tx_missing,
    )


def _attach_seen_in_window(
    pair: CandidatePair,
    seen_candidates: Sequence[RoleScore],
    mode: str,
) -> tuple[RoleScore | None, bool]:
    """Pick nearest predicted-SEEN per the cohort's window rule."""
    ftr = _to_date(pair.ftr_date)
    dx = _to_date(pair.dx_date)
    if mode == "linked" and ftr and dx:
        eligible = [
            s for s in seen_candidates if _within(s.encounter_date, ftr, dx, exclusive_left=True)
        ]
        if not eligible:
            return None, True
        return min(eligible, key=lambda s: abs((_to_date(s.encounter_date) - ftr).days)), False  # type: ignore[operator]
    if mode == "unmatched_ftr" and ftr:
        eligible = [
            s for s in seen_candidates if _within(s.encounter_date, ftr, _add_days(ftr, 90))
        ]
        if not eligible:
            return None, True
        return eligible[0], False
    if mode == "unmatched_dx" and dx:
        eligible = [
            s for s in seen_candidates if _within(s.encounter_date, _add_days(dx, -180), dx)
        ]
        if not eligible:
            return None, True
        return max(eligible, key=lambda s: _to_date(s.encounter_date)), False  # type: ignore[arg-type]
    return None, True


def _attach_treatment(
    pair: CandidatePair, treatment_candidates: Sequence[RoleScore]
) -> tuple[RoleScore | None, bool]:
    """Treatment attaches only when outcome is cancer_found."""
    if pair.dx_outcome != "cancer_found":
        return None, False
    dx_date = _to_date(pair.dx_date)
    if dx_date is None:
        return None, True
    eligible = [
        t
        for t in treatment_candidates
        if _within(t.encounter_date, dx_date, _add_days(dx_date, 180))
    ]
    if not eligible:
        return None, True
    return min(
        eligible, key=lambda t: (_to_date(t.encounter_date) - dx_date).days  # type: ignore[operator]
    ), False


def _within(
    value: str,
    lo: date,
    hi: date,
    *,
    exclusive_left: bool = False,
) -> bool:
    d = _to_date(value)
    if d is None:
        return False
    if exclusive_left:
        return lo < d <= hi
    return lo <= d <= hi


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _add_days(d: date, n: int) -> date:
    from datetime import timedelta

    return d + timedelta(days=n)


def _maybe_promote_cohort_4(
    candidates: list[EpisodeCandidate],
) -> list[EpisodeCandidate]:
    """If multiple linked pairs exist for the patient, promote each to cohort 4."""
    linked = [c for c in candidates if c.dx_encounter_id and c.ftr_encounter_id]
    if len(linked) <= 1:
        return candidates
    promoted: list[EpisodeCandidate] = []
    for c in candidates:
        if c.dx_encounter_id and c.ftr_encounter_id:
            promoted.append(
                EpisodeCandidate(
                    **{**c.__dict__, "cohort": "4", "sub_state": c.cohort}
                )
            )
        else:
            promoted.append(c)
    return promoted
