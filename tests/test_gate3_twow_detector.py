"""Gate 3 B3.2 -- adjudicated 2WW mention detector."""

from __future__ import annotations

from libs.sbar.twow_detector import TwowMentionClass, classify_twow_mention


def test_active_claim_detected() -> None:
    mention = classify_twow_mention("Plan: refer under 2WW lower GI pathway.")
    assert mention.classification is TwowMentionClass.active_claim


def test_negated_mention_not_active() -> None:
    mention = classify_twow_mention("No 2WW referral indicated today.")
    assert mention.classification is TwowMentionClass.negated


def test_historical_mention_not_active() -> None:
    mention = classify_twow_mention("Referred by me on 2WW earlier this year.")
    assert mention.classification is TwowMentionClass.historical


def test_template_title_excluded() -> None:
    mention = classify_twow_mention("2WW breast referral")
    assert mention.classification is TwowMentionClass.template_title
