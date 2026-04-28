"""Tests for Stage 2 consolidation rules."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.tidy_rules import (
    CANONICAL_MILESTONES,
    consolidate,
)


def test_canonical_milestones_kept_unchanged():
    decision = consolidate("referral", "GP referred via 2WW")
    assert decision.action == "keep"
    assert decision.new_milestone is None


def test_referral_sent_consolidates_to_referral():
    decision = consolidate("referral_sent", "Letter sent to dermatology")
    assert decision.action == "rewrite"
    assert decision.new_milestone == "referral"
    assert decision.outcome_attribute is None


def test_benign_closure_consolidates_with_cancer_excluded_outcome():
    decision = consolidate("benign_closure", "Discharged from 2WW pathway")
    assert decision.action == "rewrite"
    assert decision.new_milestone == "diagnosis_confirmed"
    assert decision.outcome_attribute == "cancer_excluded"


def test_outcome_letter_with_malignancy_consolidates_to_dx_found():
    decision = consolidate(
        "outcome_letter", "MDT outcome - malignant adenocarcinoma confirmed"
    )
    assert decision.action == "rewrite"
    assert decision.new_milestone == "diagnosis_confirmed"
    assert decision.outcome_attribute == "cancer_found"


def test_outcome_letter_with_benign_consolidates_to_dx_excluded():
    decision = consolidate(
        "outcome_letter", "Letter from clinic - all clear, discharged from pathway"
    )
    assert decision.action == "rewrite"
    assert decision.new_milestone == "diagnosis_confirmed"
    assert decision.outcome_attribute == "cancer_excluded"


def test_outcome_letter_without_diagnosis_content_deleted():
    decision = consolidate("outcome_letter", "Telephone consultation about admin")
    assert decision.action == "delete"


def test_unknown_milestone_deleted():
    decision = consolidate("context_milestone", "Random encounter text")
    assert decision.action == "delete"


def test_diagnosis_confirmed_keeps_with_outcome_inferred():
    decision = consolidate("diagnosis_confirmed", "(XE1vW) malignant rectal tumour")
    assert decision.action == "keep"
    assert decision.outcome_attribute == "cancer_found"


def test_diagnosis_confirmed_with_excluded_text():
    decision = consolidate(
        "diagnosis_confirmed", "Biopsy: no malignancy, benign findings"
    )
    assert decision.action == "keep"
    assert decision.outcome_attribute == "cancer_excluded"


def test_canonical_set_matches_plan():
    assert CANONICAL_MILESTONES == frozenset(
        {"referral", "first_seen", "diagnosis_confirmed", "treatment_started"}
    )


def test_treatment_started_kept():
    decision = consolidate("treatment_started", "Decapeptyl 1st injection started")
    assert decision.action == "keep"


def test_first_seen_kept():
    decision = consolidate("first_seen", "Seen in 2WW clinic")
    assert decision.action == "keep"
