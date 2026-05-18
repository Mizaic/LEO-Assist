"""Tests for Stage 7 auxiliary anchor attachment policy."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.assignment import assign
from services.analysis_worker.app.ncda_detector.linkage import LinkageScore
from services.analysis_worker.app.ncda_detector.pair_generator import (
    AuxiliaryAnchors,
    CandidatePair,
    RoleScore,
)


def _pair(outcome="cancer_found", ftr_date="2024-01-15", dx_date="2024-02-15"):
    return CandidatePair(
        patient_id="P1",
        ftr_encounter_id="F1",
        dx_encounter_id="D1",
        ftr_role_p=0.9,
        dx_role_p=0.9,
        dx_outcome=outcome,
        dx_outcome_p=0.95,
        gap_days=31,
        ftr_date=ftr_date,
        dx_date=dx_date,
    )


def _seen(date_str: str) -> RoleScore:
    return RoleScore(
        encounter_id=f"S-{date_str}",
        encounter_date=date_str,
        role_probabilities={"seen": 0.9},
        outcome=None,
        outcome_probability=None,
    )


def _treatment(date_str: str) -> RoleScore:
    return RoleScore(
        encounter_id=f"T-{date_str}",
        encounter_date=date_str,
        role_probabilities={"treatment": 0.9},
        outcome=None,
        outcome_probability=None,
    )


def _score_auto():
    return LinkageScore(probability=0.96, tier="auto")


def test_seen_inside_ftr_dx_window_attaches():
    seen_in = _seen("2024-01-30")
    seen_after = _seen("2024-03-01")  # AFTER Dx
    aux = AuxiliaryAnchors(patient_id="P1", seen=[seen_in, seen_after], treatment=[])
    result = assign("P1", [(_pair(), _score_auto())], aux)
    assert result.candidates[0].seen_encounter_id == "S-2024-01-30"


def test_seen_at_dx_boundary_inclusive_right():
    seen_at_dx = _seen("2024-02-15")
    aux = AuxiliaryAnchors(patient_id="P1", seen=[seen_at_dx], treatment=[])
    result = assign("P1", [(_pair(), _score_auto())], aux)
    assert result.candidates[0].seen_encounter_id == "S-2024-02-15"


def test_seen_at_ftr_boundary_exclusive_left():
    seen_on_ftr = _seen("2024-01-15")
    aux = AuxiliaryAnchors(patient_id="P1", seen=[seen_on_ftr], treatment=[])
    result = assign("P1", [(_pair(), _score_auto())], aux)
    assert result.candidates[0].seen_missing is True


def test_treatment_within_180d_post_dx_attaches():
    tx = _treatment("2024-05-01")
    aux = AuxiliaryAnchors(patient_id="P1", seen=[], treatment=[tx])
    result = assign("P1", [(_pair(), _score_auto())], aux)
    assert result.candidates[0].treatment_encounter_id == "T-2024-05-01"


def test_treatment_outside_180d_post_dx_drops():
    late_tx = _treatment("2024-12-31")
    aux = AuxiliaryAnchors(patient_id="P1", seen=[], treatment=[late_tx])
    result = assign("P1", [(_pair(), _score_auto())], aux)
    assert result.candidates[0].treatment_missing is True


def test_treatment_skipped_for_cancer_excluded():
    tx = _treatment("2024-05-01")
    aux = AuxiliaryAnchors(patient_id="P1", seen=[], treatment=[tx])
    result = assign("P1", [(_pair(outcome="cancer_excluded"), _score_auto())], aux)
    assert result.candidates[0].treatment_encounter_id is None
    assert result.candidates[0].treatment_missing is False  # not expected -> not "missing"


def test_unmatched_ftr_seen_window_is_ftr_to_ftr_plus_90d():
    pair = CandidatePair(
        patient_id="P1",
        ftr_encounter_id="F1",
        dx_encounter_id=None,
        ftr_role_p=0.9,
        dx_role_p=0.0,
        dx_outcome=None,
        dx_outcome_p=None,
        gap_days=None,
        ftr_date="2024-01-15",
        dx_date=None,
    )
    early_seen = _seen("2024-02-01")  # within 90d of FTR
    late_seen = _seen("2024-06-01")  # > 90d after FTR
    aux = AuxiliaryAnchors(patient_id="P1", seen=[early_seen, late_seen], treatment=[])
    result = assign("P1", [(pair, LinkageScore(probability=0.0, tier="review"))], aux)
    cohort_2 = [c for c in result.candidates if c.cohort == "2"]
    assert cohort_2[0].seen_encounter_id == "S-2024-02-01"
