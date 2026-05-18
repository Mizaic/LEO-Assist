"""Tests for Stage 0b - Read-code-to-NCDA-role lookup."""

from __future__ import annotations

from libs.domains.read_code_ncda_lookup import (
    KNOWN_JUNK_TOKENS,
    READ_CODE_TO_NCDA_ROLE,
    TREATMENT_DRUG_TOKENS,
    lookup_read_code,
    role_count_summary,
)


def test_lookup_returns_known_ftr_codes():
    role, outcome = READ_CODE_TO_NCDA_ROLE["XaMeA"]
    assert role == "ftr"
    assert outcome is None


def test_lookup_returns_dx_with_outcome():
    role, outcome = READ_CODE_TO_NCDA_ROLE["XE1vW"]
    assert role == "dx"
    assert outcome == "cancer_found"


def test_benign_closure_codes_have_cancer_excluded_outcome():
    role, outcome = READ_CODE_TO_NCDA_ROLE["J5031"]
    assert role == "dx"
    assert outcome == "cancer_excluded"


def test_XM0By_colonoscopy_maps_to_dx_outcome_inferred():
    """Patient 4245139757 regression: XM0By 'Colonoscopy' must be in the
    lookup as a dx anchor with outcome=None so the labeller can infer
    cancer_found vs cancer_excluded from the surrounding text.
    """
    assert "XM0By" in READ_CODE_TO_NCDA_ROLE
    role, outcome = READ_CODE_TO_NCDA_ROLE["XM0By"]
    assert role == "dx"
    assert outcome is None


def test_treatment_codes_have_no_outcome():
    role, outcome = READ_CODE_TO_NCDA_ROLE["X40EC"]
    assert role == "treatment"
    assert outcome is None


def test_seen_codes_have_no_outcome():
    role, outcome = READ_CODE_TO_NCDA_ROLE["XaPyQ"]
    assert role == "seen"
    assert outcome is None


def test_only_dx_role_has_outcome():
    """Outcome must be None unless role == 'dx'.

    Dx codes may carry None outcome when they represent investigation/procedure
    events (e.g. breast USS, prostate biopsy) where the result is not embedded
    in the coded entry.  The simple_linker treats these as lower-priority dx
    candidates, preferring outcome-bearing encounters when available.
    """
    for code, (role, outcome) in READ_CODE_TO_NCDA_ROLE.items():
        if role != "dx":
            assert outcome is None, (
                f"Read code {code} has role={role} but non-null outcome={outcome}"
            )
        else:
            assert outcome in ("cancer_found", "cancer_excluded", None), (
                f"Read code {code} has role=dx but invalid outcome={outcome!r}"
            )


def test_lookup_helper_returns_treatment_for_drug_names():
    role, outcome = lookup_read_code("DECAPEPTYL")
    assert role == "treatment"
    assert outcome is None


def test_lookup_helper_drug_name_is_case_insensitive():
    role_upper, _ = lookup_read_code("Tamoxifen")
    assert role_upper == "treatment"


def test_lookup_helper_returns_none_for_junk_tokens():
    for junk in KNOWN_JUNK_TOKENS:
        assert lookup_read_code(junk) is None, (
            f"Junk token {junk!r} should return None from lookup_read_code"
        )


def test_lookup_helper_returns_none_for_unknown_token():
    assert lookup_read_code("NEVERSEEN_XYZ_99") is None


def test_no_overlap_between_drug_tokens_and_read_codes():
    """Drug names should not also appear in the curated Read-code dict."""
    overlap = TREATMENT_DRUG_TOKENS & set(READ_CODE_TO_NCDA_ROLE.keys())
    assert not overlap, f"Drug tokens overlap with Read codes: {overlap}"


def test_no_junk_tokens_in_read_codes():
    """Junk tokens should not also appear in the curated Read-code dict."""
    overlap = KNOWN_JUNK_TOKENS & set(READ_CODE_TO_NCDA_ROLE.keys())
    assert not overlap, f"Junk tokens leaked into Read-code lookup: {overlap}"


def test_role_count_summary_covers_all_roles():
    summary = role_count_summary()
    assert set(summary.keys()) == {"ftr", "seen", "dx", "treatment", "none"}
    assert summary["ftr"] >= 5, "Need at least 5 curated FTR codes for v0"
    assert summary["dx"] >= 10, "Need at least 10 curated Dx codes for v0"
    assert summary["treatment"] >= 5, "Need at least 5 curated treatment codes"


def test_role_count_summary_totals_match_dict():
    summary = role_count_summary()
    assert sum(summary.values()) == len(READ_CODE_TO_NCDA_ROLE)


def test_dx_excluded_codes_present_in_v0():
    """Cohort 1b training requires at least a few cancer_excluded examples."""
    excluded_count = sum(
        1
        for role, outcome in READ_CODE_TO_NCDA_ROLE.values()
        if role == "dx" and outcome == "cancer_excluded"
    )
    assert excluded_count >= 3, (
        "Need at least 3 curated cancer_excluded codes for cohort 1b training"
    )
