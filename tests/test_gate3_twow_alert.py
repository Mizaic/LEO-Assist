"""Gate 3 B3.3 -- 2WW mismatch alert."""

from __future__ import annotations

from libs.sbar.twow_alert import evaluate_twow_mismatch


def test_alerts_when_structured_priority_blank_and_letter_claims_2ww() -> None:
    alert = evaluate_twow_mismatch(
        structured_priority="",
        letter_text="Plan: urgent 2WW colorectal referral.",
        referral_id="rr-1",
        run_id="run-1",
    )
    assert alert is not None
    assert alert.alert_type == "twow_priority_mismatch"
    assert "two-week-wait" in alert.message.lower()


def test_no_alert_when_structured_priority_is_2ww() -> None:
    alert = evaluate_twow_mismatch(
        structured_priority="2ww",
        letter_text="Plan: urgent 2WW colorectal referral.",
        referral_id="rr-1",
        run_id="run-1",
    )
    assert alert is None


def test_no_alert_for_negated_letter_wording() -> None:
    alert = evaluate_twow_mismatch(
        structured_priority="routine",
        letter_text="No 2WW referral indicated.",
        referral_id="rr-1",
        run_id="run-1",
    )
    assert alert is None
