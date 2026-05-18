"""Tests for Stage 7 pair assignment + cohort labelling."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.assignment import assign
from services.analysis_worker.app.ncda_detector.linkage import LinkageScore
from services.analysis_worker.app.ncda_detector.pair_generator import (
    AuxiliaryAnchors,
    CandidatePair,
    RoleScore,
)


def _pair(
    *,
    ftr_id: str | None = "F1",
    dx_id: str | None = "D1",
    outcome="cancer_found",
    ftr_date="2024-01-15",
    dx_date="2024-02-15",
):
    return CandidatePair(
        patient_id="P1",
        ftr_encounter_id=ftr_id,
        dx_encounter_id=dx_id,
        ftr_role_p=0.9,
        dx_role_p=0.9,
        dx_outcome=outcome,
        dx_outcome_p=0.95 if outcome else None,
        gap_days=(31 if ftr_id and dx_id else None),
        ftr_date=ftr_date if ftr_id else None,
        dx_date=dx_date if dx_id else None,
    )


def _score(p: float) -> LinkageScore:
    if p >= 0.95:
        tier = "auto"
    elif p >= 0.7:
        tier = "suggest"
    else:
        tier = "review"
    return LinkageScore(probability=p, tier=tier)


def _aux(seen=None, treatment=None) -> AuxiliaryAnchors:
    return AuxiliaryAnchors(patient_id="P1", seen=seen or [], treatment=treatment or [])


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


def test_per_dx_uniqueness():
    pairs = [
        (_pair(ftr_id="F1", dx_id="D1"), _score(0.96)),
        (_pair(ftr_id="F2", dx_id="D1"), _score(0.91)),  # same Dx, lower P
    ]
    result = assign("P1", pairs, _aux())
    dxs = [c.dx_encounter_id for c in result.candidates if c.dx_encounter_id]
    assert dxs == ["D1"], f"Expected D1 to bind once, got {dxs}"


def test_cohort_1a_assigned_for_cancer_found():
    pairs = [(_pair(), _score(0.96))]
    result = assign("P1", pairs, _aux())
    assert result.candidates[0].cohort == "1a"


def test_cohort_1b_assigned_for_cancer_excluded():
    pairs = [(_pair(outcome="cancer_excluded"), _score(0.96))]
    result = assign("P1", pairs, _aux())
    assert result.candidates[0].cohort == "1b"


def test_unmatched_ftr_promoted_to_cohort_2():
    pairs = [(_pair(dx_id=None), _score(0.0))]
    result = assign("P1", pairs, _aux())
    assert any(c.cohort == "2" for c in result.candidates)


def test_unmatched_cancer_found_dx_promoted_to_cohort_3():
    pairs = [(_pair(ftr_id=None), _score(0.0))]
    result = assign("P1", pairs, _aux())
    assert any(c.cohort == "3" for c in result.candidates)


def test_seen_attached_within_ftr_dx_window():
    seen = _seen("2024-01-25")
    pairs = [(_pair(), _score(0.96))]
    result = assign("P1", pairs, _aux(seen=[seen]))
    assert result.candidates[0].seen_encounter_id == "S-2024-01-25"
    assert result.candidates[0].seen_missing is False


def test_treatment_attached_only_for_cancer_found():
    tx = _treatment("2024-04-01")
    pairs_excluded = [(_pair(outcome="cancer_excluded"), _score(0.96))]
    result_excluded = assign("P1", pairs_excluded, _aux(treatment=[tx]))
    assert result_excluded.candidates[0].treatment_encounter_id is None
    assert result_excluded.candidates[0].treatment_missing is False  # not expected

    pairs_found = [(_pair(outcome="cancer_found"), _score(0.96))]
    result_found = assign("P1", pairs_found, _aux(treatment=[tx]))
    assert result_found.candidates[0].treatment_encounter_id == "T-2024-04-01"


def test_review_tier_pairs_skipped_in_assignment():
    pairs = [(_pair(), _score(0.4))]
    result = assign("P1", pairs, _aux())
    linked = [c for c in result.candidates if c.dx_encounter_id and c.ftr_encounter_id]
    assert linked == [], "Review-tier pairs should not produce linked candidates"


def test_cohort_4_when_multiple_linked_pairs():
    pairs = [
        (_pair(ftr_id="F1", dx_id="D1", ftr_date="2024-01-15", dx_date="2024-02-15"), _score(0.96)),
        (_pair(ftr_id="F2", dx_id="D2", ftr_date="2024-06-01", dx_date="2024-07-01"), _score(0.96)),
    ]
    result = assign("P1", pairs, _aux())
    cohorts = [c.cohort for c in result.candidates if c.dx_encounter_id and c.ftr_encounter_id]
    assert cohorts.count("4") == 2
    sub_states = [c.sub_state for c in result.candidates if c.cohort == "4"]
    assert "1a" in sub_states
