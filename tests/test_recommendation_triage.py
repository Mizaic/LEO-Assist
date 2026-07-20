"""Recommendation triage -- happy and non-happy / edge paths."""

from __future__ import annotations

from libs.guidance.recommendation_triage import (
    default_selected_for_triage,
    triage_recommendation,
)


class TestTriageHappy:
    def test_urgent_referral_is_full_rule(self):
        text = (
            "1.4.1 Urgently refer people with acne fulminans on the same day "
            "to the on-call hospital dermatology team."
        )
        assert triage_recommendation(text) == "full_rule"
        assert default_selected_for_triage("full_rule") is True

    def test_advice_with_population_is_narrative(self):
        text = (
            "1.2.1 Advise people with acne to use a non-alkaline synthetic "
            "detergent (syndet) cleanser."
        )
        assert triage_recommendation(text) == "trigger_plus_narrative"

    def test_information_only_is_no_rule(self):
        text = (
            "1.1.1 Give people with acne clear information tailored to their "
            "needs and concerns. Topics to cover include..."
        )
        assert triage_recommendation(text) == "no_rule"
        assert default_selected_for_triage("no_rule") is False


class TestTriageUnhappyEdges:
    def test_empty_is_no_rule(self):
        assert triage_recommendation("") == "no_rule"
        assert triage_recommendation("   ") == "no_rule"

    def test_parents_carers_discussion_is_no_rule(self):
        text = (
            "1.1.2 Include parents and carers in discussions if the person "
            "with acne would like them to be involved."
        )
        assert triage_recommendation(text) == "no_rule"

    def test_diet_evidence_statement_is_no_rule(self):
        text = (
            "1.3.1 Advise people that there is not enough evidence to support "
            "specific diets for treating acne. For general advice about diet..."
        )
        assert triage_recommendation(text) == "no_rule"
