"""Stage 10 - NCDA evidence packager.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Builds per-anchor and per-pair evidence for each EpisodeOfCare candidate
emitted by Stage 7 assignment. Output is consumed by:

  - The Stage 9a pathway timeline UI (citation popovers, traffic-light
    bands).
  - The reviewer audit log so every auto-tier decision is explainable.
  - The Stage 11 nightly drift detector (per-pair gap distributions).

This module is pure data transformation; persistence to the existing
EpisodeProvenance schema is the caller's responsibility.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Sequence

from services.analysis_worker.app.ncda_detector.assignment import EpisodeCandidate
from services.analysis_worker.app.ncda_detector.linkage_features import (
    FDS_28,
    REFERRAL_62,
    TREATMENT_31,
)
from services.analysis_worker.app.ncda_detector.pair_generator import RoleScore


@dataclass(frozen=True)
class AnchorEvidence:
    """Per-anchor evidence packaged for the UI / audit."""

    encounter_id: str
    date: str
    citation_snippet: str
    top_features: list[dict[str, float]]
    site_key: str | None = None


@dataclass(frozen=True)
class IntervalEvidence:
    """Per-interval gap + breach flags."""

    name: str
    gap_days: int
    breached: bool
    threshold_days: int


@dataclass(frozen=True)
class PathwayEvidence:
    """Top-level evidence packet for one EpisodeCandidate."""

    patient_id: str
    cohort: str
    tier: str
    sub_state: str | None
    site_key: str | None
    ftr: AnchorEvidence | None
    seen: AnchorEvidence | None
    dx: AnchorEvidence | None
    treatment: AnchorEvidence | None
    intervals: list[IntervalEvidence] = field(default_factory=list)
    intervening: list[dict] = field(default_factory=list)
    seen_missing: bool = False
    treatment_missing: bool = False
    linkage_top_features: list[dict] = field(default_factory=list)
    reason_no_outcome: str | None = None
    reason_no_ftr: str | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["ftr"] = asdict(self.ftr) if self.ftr else None
        out["seen"] = asdict(self.seen) if self.seen else None
        out["dx"] = asdict(self.dx) if self.dx else None
        out["treatment"] = asdict(self.treatment) if self.treatment else None
        return out


def build_pathway_evidence(
    candidate: EpisodeCandidate,
    *,
    encounter_index: dict[str, RoleScore],
    intervening: Sequence[RoleScore] = (),
    linkage_top_features: Sequence[dict] = (),
    site_key: str | None = None,
) -> PathwayEvidence:
    """Package per-candidate evidence for UI + audit."""
    ftr_ev = _anchor(candidate.ftr_encounter_id, encounter_index, site_key=site_key)
    seen_ev = _anchor(candidate.seen_encounter_id, encounter_index, site_key=site_key)
    dx_ev = _anchor(candidate.dx_encounter_id, encounter_index, site_key=site_key)
    tx_ev = _anchor(candidate.treatment_encounter_id, encounter_index, site_key=site_key)
    intervals = _intervals(candidate)
    intervening_payload = [
        {
            "encounter_id": e.encounter_id,
            "date": e.encounter_date,
            "predicted_role": _top_role(e),
            "predicted_role_p": _top_p(e),
        }
        for e in intervening
    ]
    return PathwayEvidence(
        patient_id=candidate.patient_id,
        cohort=candidate.cohort,
        tier=candidate.tier,
        sub_state=candidate.sub_state,
        site_key=site_key,
        ftr=ftr_ev,
        seen=seen_ev,
        dx=dx_ev,
        treatment=tx_ev,
        intervals=intervals,
        intervening=intervening_payload,
        seen_missing=candidate.seen_missing,
        treatment_missing=candidate.treatment_missing,
        linkage_top_features=list(linkage_top_features),
        reason_no_outcome=_reason_no_outcome(candidate),
        reason_no_ftr=_reason_no_ftr(candidate),
    )


def _anchor(
    encounter_id: str | None,
    encounter_index: dict[str, RoleScore],
    *,
    site_key: str | None,
) -> AnchorEvidence | None:
    if encounter_id is None:
        return None
    score = encounter_index.get(encounter_id)
    if score is None:
        return AnchorEvidence(
            encounter_id=encounter_id,
            date="",
            citation_snippet="",
            top_features=[],
            site_key=site_key,
        )
    return AnchorEvidence(
        encounter_id=encounter_id,
        date=score.encounter_date or "",
        citation_snippet=(score.text or "")[:280] if hasattr(score, "text") else "",
        top_features=[],
        site_key=site_key,
    )


def _intervals(candidate: EpisodeCandidate) -> list[IntervalEvidence]:
    out: list[IntervalEvidence] = []
    if candidate.ftr_date and candidate.dx_date:
        gap = _gap(candidate.ftr_date, candidate.dx_date)
        out.append(_interval_record("ftr_to_dx_fds_28", gap, FDS_28))
    if candidate.dx_outcome == "cancer_found":
        if candidate.dx_date and candidate.treatment_date:
            gap = _gap(candidate.dx_date, candidate.treatment_date)
            out.append(_interval_record("dx_to_treatment_31", gap, TREATMENT_31))
        if candidate.ftr_date and candidate.treatment_date:
            gap = _gap(candidate.ftr_date, candidate.treatment_date)
            out.append(_interval_record("ftr_to_treatment_62", gap, REFERRAL_62))
    if candidate.ftr_date and candidate.seen_date:
        out.append(
            _interval_record(
                "ftr_to_first_seen", _gap(candidate.ftr_date, candidate.seen_date), FDS_28
            )
        )
    return out


def _interval_record(name: str, gap_days: int, threshold: int) -> IntervalEvidence:
    return IntervalEvidence(
        name=name,
        gap_days=gap_days,
        breached=gap_days > threshold,
        threshold_days=threshold,
    )


def _gap(start: str, end: str) -> int:
    a = _to_date(start)
    b = _to_date(end)
    if a is None or b is None:
        return 0
    return (b - a).days


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _top_role(score: RoleScore) -> str:
    if not score.role_probabilities:
        return "none"
    return max(score.role_probabilities, key=score.role_probabilities.get)


def _top_p(score: RoleScore) -> float:
    if not score.role_probabilities:
        return 0.0
    return float(max(score.role_probabilities.values()))


def _reason_no_outcome(candidate: EpisodeCandidate) -> str | None:
    if candidate.cohort != "2":
        return None
    return "no_dx_in_window"


def _reason_no_ftr(candidate: EpisodeCandidate) -> str | None:
    if candidate.cohort != "3":
        return None
    return "no_ftr_in_record"
