"""Stage 10 - Breach-flag tests across cohort edge cases."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.assignment import EpisodeCandidate
from services.analysis_worker.app.ncda_detector.evidence import (
    build_pathway_evidence,
)
from services.analysis_worker.app.ncda_detector.pair_generator import RoleScore


def _candidate(
    *,
    ftr_date="2024-01-15",
    seen_date="2024-01-25",
    dx_date="2024-02-15",
    treatment_date="2024-03-01",
    outcome="cancer_found",
    cohort="1a",
    tier="auto",
):
    return EpisodeCandidate(
        patient_id="P1",
        cohort=cohort,
        tier=tier,
        ftr_encounter_id="F1",
        ftr_date=ftr_date,
        seen_encounter_id="S1",
        seen_date=seen_date,
        dx_encounter_id="D1",
        dx_date=dx_date,
        dx_outcome=outcome,
        treatment_encounter_id="T1",
        treatment_date=treatment_date,
        linkage_probability=0.96,
    )


def _index() -> dict[str, RoleScore]:
    def _score(eid: str, dt: str, role: str, outcome=None) -> RoleScore:
        return RoleScore(
            encounter_id=eid,
            encounter_date=dt,
            role_probabilities={role: 0.9},
            outcome=outcome,
            outcome_probability=0.95 if outcome else None,
        )

    return {
        "F1": _score("F1", "2024-01-15", "ftr"),
        "S1": _score("S1", "2024-01-25", "seen"),
        "D1": _score("D1", "2024-02-15", "dx", outcome="cancer_found"),
        "T1": _score("T1", "2024-03-01", "treatment"),
    }


def test_evidence_packages_all_anchors_for_cohort_1a():
    ev = build_pathway_evidence(_candidate(), encounter_index=_index())
    assert ev.ftr is not None
    assert ev.seen is not None
    assert ev.dx is not None
    assert ev.treatment is not None


def test_breach_flags_under_thresholds_clear():
    ev = build_pathway_evidence(_candidate(), encounter_index=_index())
    intervals = {iv.name: iv for iv in ev.intervals}
    assert intervals["ftr_to_dx_fds_28"].breached is True  # 31 > 28
    assert intervals["dx_to_treatment_31"].breached is False  # 15 <= 31
    assert intervals["ftr_to_treatment_62"].breached is False  # 46 <= 62


def test_referral_62_breach_fires():
    candidate = _candidate(
        ftr_date="2024-01-01",
        dx_date="2024-04-01",  # 91 days
        treatment_date="2024-05-01",  # 30 days post-Dx
    )
    ev = build_pathway_evidence(candidate, encounter_index=_index())
    intervals = {iv.name: iv for iv in ev.intervals}
    assert intervals["ftr_to_treatment_62"].breached is True
    assert intervals["ftr_to_dx_fds_28"].breached is True


def test_treatment_31_breach_fires():
    candidate = _candidate(
        treatment_date="2024-04-01",  # 46 days post-Dx
    )
    ev = build_pathway_evidence(candidate, encounter_index=_index())
    intervals = {iv.name: iv for iv in ev.intervals}
    assert intervals["dx_to_treatment_31"].breached is True


def test_cancer_excluded_drops_treatment_intervals():
    candidate = _candidate(
        outcome="cancer_excluded",
        treatment_date=None,
        cohort="1b",
    )
    ev = build_pathway_evidence(candidate, encounter_index=_index())
    interval_names = {iv.name for iv in ev.intervals}
    assert "dx_to_treatment_31" not in interval_names
    assert "ftr_to_treatment_62" not in interval_names


def test_cohort_2_carries_reason_no_outcome():
    candidate = EpisodeCandidate(
        patient_id="P1",
        cohort="2",
        tier="review",
        ftr_encounter_id="F1",
        ftr_date="2024-01-15",
        seen_encounter_id=None,
        seen_date=None,
        dx_encounter_id=None,
        dx_date=None,
        dx_outcome=None,
        treatment_encounter_id=None,
        treatment_date=None,
        linkage_probability=0.0,
    )
    ev = build_pathway_evidence(candidate, encounter_index=_index())
    assert ev.reason_no_outcome == "no_dx_in_window"


def test_cohort_3_carries_reason_no_ftr():
    candidate = EpisodeCandidate(
        patient_id="P1",
        cohort="3",
        tier="review",
        ftr_encounter_id=None,
        ftr_date=None,
        seen_encounter_id=None,
        seen_date=None,
        dx_encounter_id="D1",
        dx_date="2024-04-01",
        dx_outcome="cancer_found",
        treatment_encounter_id="T1",
        treatment_date="2024-05-15",
        linkage_probability=0.0,
    )
    ev = build_pathway_evidence(candidate, encounter_index=_index())
    assert ev.reason_no_ftr == "no_ftr_in_record"


def test_evidence_to_dict_serialisable():
    ev = build_pathway_evidence(_candidate(), encounter_index=_index())
    payload = ev.to_dict()
    assert payload["cohort"] == "1a"
    assert isinstance(payload["intervals"], list)
