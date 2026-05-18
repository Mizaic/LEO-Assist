"""Tests for SBAR coherence check.

Atlas trace:
  DI: DI-CC0BD732
"""

from __future__ import annotations

from libs.sbar.coherence_check import (
    check_code_narrative_drift,
    check_narrative_contradiction,
    run_coherence_checks,
)


def test_no_contradiction_when_assessment_neutral():
    flag = check_narrative_contradiction(
        assessment_md="Findings consistent with breast cancer.",
        recommendation_md="Refer to oncology MDT.",
    )
    assert flag is None


def test_contradiction_detected_when_negation_meets_urgent_recommendation():
    flag = check_narrative_contradiction(
        assessment_md="No current evidence of malignancy at this time.",
        recommendation_md="Initiate urgent oncology referral via two-week wait pathway.",
    )
    assert flag is not None
    assert flag.code == "narrative_contradiction"
    assert flag.severity == "high"


def test_contradiction_skipped_when_recommendation_is_routine():
    flag = check_narrative_contradiction(
        assessment_md="No evidence of malignancy.",
        recommendation_md="Continue routine annual review.",
    )
    assert flag is None


def test_code_narrative_drift_detected_when_site_missing_from_text():
    flag = check_code_narrative_drift(
        canonical_concept_id="254837009",
        canonical_display_name="Malignant tumor of breast",
        suspected_site="breast",
        sbar_markdown="Patient presents with epigastric pain. UGI investigations ongoing.",
    )
    assert flag is not None
    assert flag.code == "code_narrative_drift"


def test_code_narrative_drift_passes_when_site_in_text():
    flag = check_code_narrative_drift(
        canonical_concept_id="254837009",
        canonical_display_name="Malignant tumor of breast",
        suspected_site="breast",
        sbar_markdown="Patient with right breast lesion. Mammography confirmed.",
    )
    assert flag is None


def test_code_narrative_drift_passes_when_display_words_in_text():
    flag = check_code_narrative_drift(
        canonical_concept_id="254837009",
        canonical_display_name="Malignant tumor of pancreas",
        suspected_site="upper_gi",
        sbar_markdown="Patient diagnosed with pancreatic malignant tumor.",
    )
    assert flag is None


def test_run_coherence_checks_returns_both_flags():
    flags = run_coherence_checks(
        assessment_md="No evidence of malignancy.",
        recommendation_md="Initiate urgent oncology referral 2WW.",
        sbar_markdown="UGI symptoms only.",
        canonical_concept_id="254837009",
        canonical_display_name="Malignant tumor of breast",
        suspected_site="breast",
    )
    codes = {f.code for f in flags}
    assert "narrative_contradiction" in codes
    assert "code_narrative_drift" in codes


def test_run_coherence_checks_returns_empty_when_clean():
    flags = run_coherence_checks(
        assessment_md="Confirmed breast cancer.",
        recommendation_md="Refer to oncology MDT.",
        sbar_markdown="Right breast lesion confirmed on mammography.",
        canonical_concept_id="254837009",
        canonical_display_name="Malignant tumor of breast",
        suspected_site="breast",
    )
    assert flags == []
