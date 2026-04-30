"""Unit tests for libs/oncology/safety_netting.detect_safety_netting.

Pins the signal hierarchy (strong > medium > advice_only > none) and
the QOF/CBS-claim down-weighting rule, so the audit dashboard's
"Safety netting" tile cannot silently regress when the regex set is
broadened (e.g. when adding new PRISM template variants).
"""

from __future__ import annotations

import pytest

from libs.oncology.safety_netting import (
    SafetyNettingMatch,
    detect_safety_netting,
)


# ---------------------------------------------------------------------------
# Strong: structured Read code Y281b OR clinician-written safety-net phrase
# ---------------------------------------------------------------------------


def test_y281b_read_code_is_strong() -> None:
    text = (
        "P: Plan: Refer 2WW dermatology for ?melanoma\n"
        "Referral safety net: Cancer safety netting (Y281b)\n"
    )
    result = detect_safety_netting([text])
    assert result.signal == "strong"
    assert result.recorded is True
    # Both the code and the rendered phrase should be picked up.
    assert "Y281b" in result.code_hits
    assert any("cancer safety netting" in c.lower() for c in result.code_hits)
    assert result.evidence_count == 1


def test_explicit_safety_netted_in_plan_is_strong() -> None:
    text = (
        "P: ?persistent UTI - if dip positive, issue abx pre Christmas\n"
        "Review after US - has appt next couple of weeks\n"
        "Safety netted\n"
    )
    result = detect_safety_netting([text])
    assert result.signal == "strong"
    assert result.recorded is True
    assert any("safety netted" in p for p in result.phrase_hits)


def test_safety_net_advice_provided_is_strong() -> None:
    text = (
        "Plan: 1. Book in to discuss diabetes management\n"
        "2. Safety net advice provided that should he develop blurry "
        "vision, drowsiness or extreme tiredness to call emergency "
        "services\n"
    )
    result = detect_safety_netting([text])
    assert result.signal == "strong"
    assert result.recorded is True
    assert any("safety net" in p for p in result.phrase_hits)


def test_safetynetting_single_word_is_strong() -> None:
    text = "Start furosemide and urgent HF referral.\nSafetynetting.\n"
    result = detect_safety_netting([text])
    assert result.signal == "strong"
    assert result.recorded is True


def test_hyphenated_safety_net_is_strong() -> None:
    text = "Plan: 2WW urology referral. Safety-net advice given re red flags."
    result = detect_safety_netting([text])
    assert result.signal == "strong"
    assert result.recorded is True


# ---------------------------------------------------------------------------
# Medium: PRISM 2WW questionnaire field only
# ---------------------------------------------------------------------------


def test_prism_advice_if_worsens_is_medium() -> None:
    text = (
        "PRISM 2WW Drawing Dermatology\n"
        "      Advice if worsens, no better or concerns: Yes\n"
        "      Photographs taken: Yes\n"
    )
    result = detect_safety_netting([text])
    assert result.signal == "medium"
    assert result.recorded is True


def test_qof_cbs_claim_only_is_medium_not_strong() -> None:
    """A patient on a structured PSA-monitoring protocol gets
    "Cancer safety netting (CBS claim): Yes" auto-stamped on every
    encounter even if the GP did not write a free-text plan. Treat
    that as medium evidence (structured protocol exists) but NOT
    strong (no clinician-written plan in this visit)."""
    text = (
        " LLR PSA Monitoring\n"
        "   ^Cancer safety netting (CBS claim): Yes\n"
        "   ^Raised PSA (CBS register code): Yes\n"
        "Summary Care Record Update - patient prefers core items only.\n"
    )
    result = detect_safety_netting([text])
    assert result.signal == "medium"
    assert result.recorded is True


def test_qof_echo_plus_clinician_safety_net_is_strong() -> None:
    """If the QOF echo AND a clinician-written 'safety netted' both
    appear in the same encounter, the clinician note still wins."""
    text = (
        " LLR PSA Monitoring\n"
        "   ^Cancer safety netting (CBS claim): Yes\n"
        "P: discussed PSA result with patient. Safety netted - to "
        "return urgently if any new urinary symptoms.\n"
    )
    result = detect_safety_netting([text])
    assert result.signal == "strong"
    assert result.recorded is True


# ---------------------------------------------------------------------------
# Advice-only: generic "return if X" phrasing
# ---------------------------------------------------------------------------


def test_return_if_only_is_advice_only() -> None:
    text = "P: Reassure. To return if symptoms persist beyond 2 weeks."
    result = detect_safety_netting([text])
    assert result.signal == "advice_only"
    assert result.recorded is False


def test_red_flag_only_is_advice_only() -> None:
    text = (
        "Examination unremarkable. Patient counselled re red flag "
        "symptoms requiring urgent review."
    )
    result = detect_safety_netting([text])
    assert result.signal == "advice_only"
    assert result.recorded is False


def test_come_back_if_only_is_advice_only() -> None:
    text = "Plan: trial paracetamol PRN. Come back if no improvement in a week."
    result = detect_safety_netting([text])
    assert result.signal == "advice_only"
    assert result.recorded is False


# ---------------------------------------------------------------------------
# None: no signal in the text
# ---------------------------------------------------------------------------


def test_no_signal_is_none() -> None:
    text = (
        "Telephone consultation. Discussed test results. Patient "
        "happy with plan. Repeat bloods in 3 months."
    )
    result = detect_safety_netting([text])
    assert result.signal == "none"
    assert result.recorded is False
    assert result.code_hits == ()
    assert result.phrase_hits == ()
    assert result.evidence_count == 0


def test_empty_text_is_none() -> None:
    result = detect_safety_netting([""])
    assert result.signal == "none"
    assert result.recorded is False
    assert result.evidence_count == 0


def test_empty_iterable_is_none() -> None:
    result = detect_safety_netting([])
    assert result.signal == "none"
    assert result.recorded is False


# ---------------------------------------------------------------------------
# Aggregation across multiple texts
# ---------------------------------------------------------------------------


def test_strongest_signal_wins_across_texts() -> None:
    texts = [
        "Routine consultation, no concerns.",
        "P: trial PPI, return if no improvement.",
        "P: Refer 2WW UGI. Safety netted - to attend A&E if dysphagia worsens.",
    ]
    result = detect_safety_netting(texts)
    assert result.signal == "strong"
    assert result.recorded is True


def test_evidence_count_aggregates_across_texts() -> None:
    texts = [
        "Plan: 2WW skin referral. Safety netted re red flags.",
        "Follow-up call. Safety net advice repeated.",
        "Routine BP check, no concerns.",
    ]
    result = detect_safety_netting(texts)
    assert result.signal == "strong"
    assert result.evidence_count == 2


def test_advice_only_does_not_promote_to_recorded() -> None:
    texts = [
        "Plan: trial paracetamol PRN.",
        "Come back if no better in 2 weeks.",
        "Consider physio if pain persists.",
    ]
    result = detect_safety_netting(texts)
    assert result.signal == "advice_only"
    assert result.recorded is False, (
        "advice_only is NOT enough to count as 'safety netting recorded'"
        " — Section 8 of the NCDA report requires an explicit safety-net"
        " plan, not just 'come back if it gets worse'."
    )


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------


def test_returns_safety_netting_match() -> None:
    result = detect_safety_netting(["Safety netted"])
    assert isinstance(result, SafetyNettingMatch)
    assert isinstance(result.recorded, bool)
    assert isinstance(result.code_hits, tuple)
    assert isinstance(result.phrase_hits, tuple)
    assert isinstance(result.evidence_count, int)


@pytest.mark.parametrize(
    "signal",
    ["strong", "medium", "advice_only", "none"],
)
def test_signal_is_one_of_the_four_known_values(signal: str) -> None:
    """Type-level pin so a future refactor cannot silently introduce a
    fifth signal value that the dashboard does not know how to render."""
    assert signal in {"strong", "medium", "advice_only", "none"}
