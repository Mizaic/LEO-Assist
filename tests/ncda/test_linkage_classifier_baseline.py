"""Tests for Stage 6 linkage classifier features + training baseline."""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from pathlib import Path

from services.analysis_worker.app.ncda_detector.linkage import LinkageClassifier
from services.analysis_worker.app.ncda_detector.linkage_features import (
    PairContext,
    extract_pair_features,
    gap_features,
    intervening_histogram,
    role_probability_features,
    vector_cosine_features,
)
from services.analysis_worker.app.ncda_detector.pair_generator import (
    CandidatePair,
    RoleScore,
)
from services.training_worker.app.ncda_linkage_trainer import train_linkage_classifier


def _pair(
    *,
    gap=30,
    ftr_id="F1",
    dx_id="D1",
    ftr_p=0.9,
    dx_p=0.9,
    outcome="cancer_found",
    outcome_p=0.95,
):
    return CandidatePair(
        patient_id="P1",
        ftr_encounter_id=ftr_id,
        dx_encounter_id=dx_id,
        ftr_role_p=ftr_p,
        dx_role_p=dx_p,
        dx_outcome=outcome,
        dx_outcome_p=outcome_p,
        gap_days=gap,
        ftr_date="2024-01-15",
        dx_date="2024-02-15",
    )


def _ctx(intervening=None):
    ftr = RoleScore(
        encounter_id="F1",
        encounter_date="2024-01-15",
        role_probabilities={"ftr": 0.9},
        outcome=None,
        outcome_probability=None,
    )
    dx = RoleScore(
        encounter_id="D1",
        encounter_date="2024-02-15",
        role_probabilities={"dx": 0.9},
        outcome="cancer_found",
        outcome_probability=0.95,
    )
    return PairContext(
        ftr_encounter=ftr,
        dx_encounter=dx,
        intervening=intervening or [],
    )


def test_gap_features_breach_flags():
    feats = gap_features(_pair(gap=30))
    assert feats["gap_days"] == 30
    assert feats["gap_breaches_28"] == 1
    assert feats["gap_breaches_62"] == 0


def test_gap_features_negative_window():
    feats = gap_features(_pair(gap=-5))
    assert feats["gap_breaches_negative"] == 1


def test_role_probability_features_outcome_one_hot():
    feats = role_probability_features(_pair(outcome="cancer_excluded"))
    assert feats["dx_is_cancer_excluded"] == 1
    assert feats["dx_is_cancer_found"] == 0


def test_intervening_histogram_counts_by_role():
    extra = RoleScore(
        encounter_id="MID",
        encounter_date="2024-02-01",
        role_probabilities={"seen": 0.95},
        outcome=None,
        outcome_probability=None,
    )
    feats = intervening_histogram(_ctx([extra]))
    assert feats["between_seen"] == 1
    assert feats["between_ftr"] == 0


def test_vector_cosine_features_no_vectors_zero():
    feats = vector_cosine_features(_ctx())
    assert feats["vec_cosine_anchor"] == 0.0


def test_extract_pair_features_includes_aux_anchors():
    seen = RoleScore(
        encounter_id="S1",
        encounter_date="2024-01-25",
        role_probabilities={"seen": 0.9},
        outcome=None,
        outcome_probability=None,
    )
    treatment = RoleScore(
        encounter_id="T1",
        encounter_date="2024-04-01",
        role_probabilities={"treatment": 0.9},
        outcome=None,
        outcome_probability=None,
    )
    feats = extract_pair_features(
        _pair(),
        _ctx(),
        seen_encounters=[seen],
        treatment_encounters=[treatment],
    )
    assert feats["seen_present"] == 1
    assert feats["treatment_present"] == 1
    assert feats["days_ftr_to_first_seen"] == 10.0
    assert feats["days_dx_to_first_treatment"] == 46.0


def _build_training_rows():
    rows = []
    for i in range(20):
        feats = extract_pair_features(
            _pair(gap=15 + i, outcome="cancer_found"),
            _ctx(),
            seen_encounters=[],
            treatment_encounters=[],
        )
        rows.append({"features": feats, "label": 1, "weight": 1.0})
    for i in range(20):
        feats = extract_pair_features(
            _pair(gap=200 + i, ftr_p=0.4, dx_p=0.4),
            _ctx(),
            seen_encounters=[],
            treatment_encounters=[],
        )
        rows.append({"features": feats, "label": 0, "weight": 1.0})
    return rows


def test_linkage_classifier_trains_and_loads(tmp_path: Path):
    artifact = tmp_path / "ncda_linkage.joblib"
    result = train_linkage_classifier(
        _build_training_rows(), artifact_path=artifact
    )
    assert artifact.exists()
    assert result.n_positive > 0
    assert result.n_negative > 0
    clf = LinkageClassifier(artifact)
    score = clf.score_one(
        extract_pair_features(
            _pair(gap=20, outcome="cancer_found"),
            _ctx(),
            seen_encounters=[],
            treatment_encounters=[],
        )
    )
    assert score.tier in {"auto", "suggest", "review"}
    assert 0.0 <= score.probability <= 1.0


def test_linkage_classifier_separates_positive_from_negative(tmp_path: Path):
    """Sanity: easy positive scores high; easy negative scores lower."""
    artifact = tmp_path / "ncda_linkage.joblib"
    train_linkage_classifier(_build_training_rows(), artifact_path=artifact)
    clf = LinkageClassifier(artifact)
    pos = clf.score_one(
        extract_pair_features(
            _pair(gap=15),
            _ctx(),
            seen_encounters=[],
            treatment_encounters=[],
        )
    )
    neg = clf.score_one(
        extract_pair_features(
            _pair(gap=300, ftr_p=0.3, dx_p=0.3),
            _ctx(),
            seen_encounters=[],
            treatment_encounters=[],
        )
    )
    assert pos.probability > neg.probability
