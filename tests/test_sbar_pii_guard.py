"""Regression tests for libs/sbar/pii_guard.py.

Covers the referral-000049823847 bug: the SBAR Situation prompt was
supplied with the patient's ``birth_date`` (to compute age) and the model
cited it verbatim as an inline evidence date for an unrelated clause --
"...pathway [1955-04-09]" -- which is both a fabricated citation and a
direct patient identifier leaking into the narrative (rule 9 of
SBAR_SITUATION_SYSTEM_V1 / SBAR_BACKGROUND_SYSTEM_V1).
"""

from __future__ import annotations

from libs.sbar.pii_guard import strip_dob_citations


def test_strips_iso_dob_citation_matching_the_real_bug():
    markdown = (
        "This 71-year-old woman needs referral assessment now for an "
        "urgent cancer pathway, but the request conflicts between 2WW "
        "and the Serious Non-Specific Symptoms pathway [1955-04-09]. "
        "The headline trigger is concern for cancer [Document date not "
        "stated]."
    )

    cleaned, stripped = strip_dob_citations(markdown, "1955-04-09")

    assert stripped is True
    assert "1955-04-09" not in cleaned
    assert "[Document date not stated]" in cleaned
    assert (
        "conflicts between 2WW and the Serious Non-Specific Symptoms "
        "pathway." in cleaned
    )


def test_strips_uk_and_us_slash_formats_of_the_same_dob():
    for surface in ("[09/04/1955]", "[04/09/1955]", "[9/4/1955]"):
        markdown = f"Some claim{surface}."
        cleaned, stripped = strip_dob_citations(markdown, "1955-04-09")
        assert stripped is True, surface
        assert "1955" not in cleaned


def test_strips_month_name_formats_of_the_same_dob():
    for surface in ("[9 April 1955]", "[April 9, 1955]", "[9 Apr 1955]"):
        markdown = f"Some claim{surface}."
        cleaned, stripped = strip_dob_citations(markdown, "1955-04-09")
        assert stripped is True, surface


def test_leaves_genuine_evidence_dates_untouched():
    markdown = (
        "Unilateral nipple discharge is recorded in the referral form. " "[2026-03-19]"
    )

    cleaned, stripped = strip_dob_citations(markdown, "1955-04-09")

    assert stripped is False
    assert cleaned == markdown


def test_noop_when_birth_date_missing():
    markdown = "A claim with a real date [2026-03-19]."

    cleaned, stripped = strip_dob_citations(markdown, None)

    assert stripped is False
    assert cleaned == markdown


def test_noop_on_empty_markdown():
    cleaned, stripped = strip_dob_citations("", "1955-04-09")

    assert stripped is False
    assert cleaned == ""


def test_only_strips_the_matching_bracket_not_others_nearby():
    markdown = "First fact [2026-03-19]. Second fact [1955-04-09]. Third fact [2015]."

    cleaned, stripped = strip_dob_citations(markdown, "1955-04-09")

    assert stripped is True
    assert "[2026-03-19]" in cleaned
    assert "[2015]" in cleaned
    assert "1955-04-09" not in cleaned
