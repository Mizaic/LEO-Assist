"""Tests for Stage 5 candidate pair generator."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.pair_generator import (
    PairThresholds,
    PairWindow,
    RoleScore,
    generate_pairs,
)


def _score(
    encounter_id: str,
    encounter_date: str,
    role: str,
    p: float = 0.9,
    outcome: str | None = None,
    outcome_p: float | None = None,
) -> RoleScore:
    role_probs = {role: p}
    return RoleScore(
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role_probabilities=role_probs,
        outcome=outcome,
        outcome_probability=outcome_p,
    )


def test_paired_ftr_dx_emits_one_pair():
    ftr = _score("F1", "2024-01-15", "ftr")
    dx = _score("D1", "2024-02-15", "dx", outcome="cancer_found", outcome_p=0.95)
    pairs, aux = generate_pairs(patient_id="P1", scores=[ftr, dx])
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.ftr_encounter_id == "F1"
    assert pair.dx_encounter_id == "D1"
    assert pair.gap_days == 31
    assert pair.dx_outcome == "cancer_found"


def test_unmatched_ftr_emits_singleton():
    ftr = _score("F1", "2024-01-15", "ftr")
    pairs, _ = generate_pairs(patient_id="P1", scores=[ftr])
    assert len(pairs) == 1
    assert pairs[0].dx_encounter_id is None
    assert pairs[0].ftr_encounter_id == "F1"


def test_unmatched_dx_cancer_found_emits_cohort3_singleton():
    dx = _score("D1", "2024-05-01", "dx", outcome="cancer_found", outcome_p=0.92)
    pairs, _ = generate_pairs(patient_id="P1", scores=[dx])
    assert len(pairs) == 1
    assert pairs[0].ftr_encounter_id is None
    assert pairs[0].dx_outcome == "cancer_found"


def test_unmatched_dx_cancer_excluded_singleton_is_dropped():
    dx = _score("D1", "2024-05-01", "dx", outcome="cancer_excluded", outcome_p=0.88)
    pairs, _ = generate_pairs(patient_id="P1", scores=[dx])
    assert pairs == []


def test_window_drops_pairs_outside_range():
    ftr = _score("F1", "2024-01-01", "ftr")
    dx = _score("D1", "2025-06-01", "dx", outcome="cancer_found", outcome_p=0.9)
    pairs, _ = generate_pairs(
        patient_id="P1", scores=[ftr, dx], window=PairWindow(min_gap_days=-90, max_gap_days=200)
    )
    full_pairs = [p for p in pairs if p.ftr_encounter_id and p.dx_encounter_id]
    assert full_pairs == [], "FTR-Dx pair outside window should not produce a paired record"
    singletons = [p for p in pairs if p.ftr_encounter_id is None or p.dx_encounter_id is None]
    assert len(singletons) == 2, "Both FTR and cancer-found Dx should emit singletons"


def test_threshold_filters_low_probability_anchors():
    ftr = _score("F1", "2024-01-15", "ftr", p=0.3)
    dx = _score("D1", "2024-02-15", "dx", p=0.4, outcome="cancer_found", outcome_p=0.9)
    pairs, _ = generate_pairs(
        patient_id="P1",
        scores=[ftr, dx],
        thresholds=PairThresholds(ftr=0.5, dx=0.5),
    )
    assert pairs == []


def test_seen_and_treatment_emitted_to_aux_table():
    seen = _score("S1", "2024-01-25", "seen")
    treatment = _score("T1", "2024-04-01", "treatment")
    pairs, aux = generate_pairs(patient_id="P1", scores=[seen, treatment])
    assert pairs == []
    assert aux.seen[0].encounter_id == "S1"
    assert aux.treatment[0].encounter_id == "T1"


def test_multi_ftr_with_dx_creates_pairs_for_each_ftr():
    ftr_a = _score("F1", "2024-01-01", "ftr")
    ftr_b = _score("F2", "2024-03-01", "ftr")
    dx = _score("D1", "2024-04-01", "dx", outcome="cancer_found", outcome_p=0.9)
    pairs, _ = generate_pairs(patient_id="P1", scores=[ftr_a, ftr_b, dx])
    assert len(pairs) == 2
    assert {p.ftr_encounter_id for p in pairs} == {"F1", "F2"}


def test_pair_negative_gap_within_window_kept():
    """Dx that arrives BEFORE the FTR (rare but real on back-dated entries)."""
    dx = _score("D1", "2024-01-15", "dx", outcome="cancer_found", outcome_p=0.92)
    ftr = _score("F1", "2024-02-01", "ftr")
    pairs, _ = generate_pairs(patient_id="P1", scores=[ftr, dx])
    assert len(pairs) == 1
    assert pairs[0].gap_days == -17
