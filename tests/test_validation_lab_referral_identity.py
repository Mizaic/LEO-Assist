"""Tests for Care-ready referral letter identity fill.

Atlas: DI-3002D641 / VT-B79AF7AC
"""

from __future__ import annotations

from libs.validation_lab.referral_identity import fill_referral_identity


def test_fill_replaces_common_identity_tokens() -> None:
    text = (
        "Dear Colleague, I refer [Patient Name], DOB [DOB]. "
        "Yours sincerely, [GP Name]"
    )
    out = fill_referral_identity(
        text,
        patient_name="Jane Doe",
        birth_date="1978-07-20",
        gp_name="Riverside Surgery",
    )
    assert "[Patient Name]" not in out
    assert "[DOB]" not in out
    assert "[GP Name]" not in out
    assert "Jane Doe" in out
    assert "1978-07-20" in out
    assert "Riverside Surgery" in out


def test_fill_leaves_tokens_when_value_missing() -> None:
    text = "Refer [Patient Name], DOB [DOB]."
    out = fill_referral_identity(text, patient_name="Jane Doe")
    assert "Jane Doe" in out
    assert "[DOB]" in out


def test_fill_is_case_insensitive_and_preserves_other_brackets() -> None:
    text = "See [patient name] and keep [Urgency]."
    out = fill_referral_identity(text, patient_name="Sam Lee")
    assert "Sam Lee" in out
    assert "[Urgency]" in out
