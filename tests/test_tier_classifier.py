"""Tests for libs/coding_engine/tier_classifier.py -- three-tier decision engine.

Safety-critical verification matrix covering all tier boundaries, assertion
types, surface form statuses, and mode-dependent behaviour.

Tier 1: auto-code (high confidence, approved surface form)
Tier 2: code with audit flag (autonomous) / review queue (HITL)
Tier 3: do not code (autonomous) / review queue (HITL)
"""

from __future__ import annotations

import pytest

from libs.coding_engine.tier_classifier import TierDecision, classify_tier


# -- Tier 3: hard gates that always prevent auto-coding --------------------


class TestTier3ContextFailure:

    def test_context_failure_autonomous(self):
        d = classify_tier(
            assertion="present",
            context_failed=True,
            terminology_score=1.0,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 3
        assert d.decision == "not_coded"
        assert d.reason == "context_failure"

    def test_context_failure_hitl(self):
        d = classify_tier(
            assertion="present",
            context_failed=True,
            terminology_score=1.0,
            surface_form_status="approved",
            coding_mode="hitl",
        )
        assert d.tier == 3
        assert d.decision == "route_to_review"
        assert d.reason == "context_failure"


class TestTier3DisorderVerdicts:

    def test_informational_autonomous(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.98,
            surface_form_status="approved",
            coding_mode="autonomous",
            disorder_verdict="informational",
        )
        assert d.tier == 3
        assert d.decision == "not_coded"
        assert d.reason == "informational"

    def test_uncertain_disorder_autonomous(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.98,
            surface_form_status="approved",
            coding_mode="autonomous",
            disorder_verdict="uncertain",
        )
        assert d.tier == 3
        assert d.decision == "not_coded"
        assert d.reason == "uncertain_assertion"


class TestTier3NonCodeableAssertions:

    @pytest.mark.parametrize("assertion", ["absent", "declined", "hypothetical"])
    def test_blocked_assertions_autonomous(self, assertion):
        d = classify_tier(
            assertion=assertion,
            context_failed=False,
            terminology_score=0.99,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 3
        assert d.decision == "not_coded"
        assert d.reason == "non_codeable_assertion"

    @pytest.mark.parametrize("assertion", ["absent", "declined", "hypothetical"])
    def test_blocked_assertions_hitl(self, assertion):
        d = classify_tier(
            assertion=assertion,
            context_failed=False,
            terminology_score=0.99,
            surface_form_status="approved",
            coding_mode="hitl",
        )
        assert d.tier == 3
        assert d.decision == "route_to_review"

    def test_possible_is_tier3(self):
        d = classify_tier(
            assertion="possible",
            context_failed=False,
            terminology_score=0.99,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 3
        assert d.reason == "uncertain_assertion"


# -- Tier 1: auto-code gates -----------------------------------------------


class TestTier1AutoCode:

    def test_approved_surface_form_high_score(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.96,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 1
        assert d.decision == "auto_coded"
        assert d.reason == "surface_form_match"

    def test_high_score_no_surface_form(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.97,
            surface_form_status="",
            coding_mode="autonomous",
        )
        assert d.tier == 1
        assert d.decision == "auto_coded"
        assert d.reason == "high_confidence"

    def test_exactly_at_threshold(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.95,
            surface_form_status="approved",
            coding_mode="hitl",
        )
        assert d.tier == 1
        assert d.decision == "auto_coded"

    def test_just_below_tier1_threshold(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.94,
            surface_form_status="",
            coding_mode="autonomous",
        )
        assert d.tier != 1


# -- Tier 2: medium confidence or qualifier assertions ----------------------


class TestTier2MediumConfidence:

    def test_medium_score_autonomous(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.80,
            surface_form_status="",
            coding_mode="autonomous",
        )
        assert d.tier == 2
        assert d.decision == "coded_with_flag"
        assert d.reason == "medium_confidence"

    def test_medium_score_hitl(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.80,
            surface_form_status="",
            coding_mode="hitl",
        )
        assert d.tier == 2
        assert d.decision == "route_to_review"

    def test_pending_surface_form(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.85,
            surface_form_status="pending",
            coding_mode="autonomous",
        )
        assert d.tier == 2
        assert d.decision == "coded_with_flag"
        assert d.reason == "pending_surface_form"


class TestTier2QualifierAssertions:

    @pytest.mark.parametrize("assertion", ["historical", "family"])
    def test_qualifier_assertions_autonomous(self, assertion):
        d = classify_tier(
            assertion=assertion,
            context_failed=False,
            terminology_score=0.99,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 2
        assert d.decision == "coded_with_flag"
        assert d.reason == "qualifier_assertion"

    @pytest.mark.parametrize("assertion", ["historical", "family"])
    def test_qualifier_assertions_hitl(self, assertion):
        d = classify_tier(
            assertion=assertion,
            context_failed=False,
            terminology_score=0.99,
            surface_form_status="approved",
            coding_mode="hitl",
        )
        assert d.tier == 2
        assert d.decision == "route_to_review"


# -- Tier 3 fallthrough: low confidence ------------------------------------


class TestTier3LowConfidence:

    def test_very_low_score(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.30,
            surface_form_status="",
            coding_mode="autonomous",
        )
        assert d.tier == 3
        assert d.decision == "not_coded"
        assert d.reason == "low_confidence"

    def test_below_tier2_threshold(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=0.69,
            surface_form_status="",
            coding_mode="autonomous",
        )
        assert d.tier == 3
        assert d.reason == "low_confidence"


# -- TierDecision dataclass ------------------------------------------------


class TestTierDecisionDataclass:

    def test_frozen(self):
        d = TierDecision(tier=1, decision="auto_coded", reason="test")
        with pytest.raises(AttributeError):
            d.tier = 2  # type: ignore[misc]


# -- Priority ordering: Tier 3 gates override Tier 1 signals ----------------


class TestTierPriorityOrdering:
    """Verify that Tier 3 gates (context failure, bad assertion, bad disorder
    verdict) always win over high terminology score / approved surface form."""

    def test_context_failure_overrides_perfect_score(self):
        d = classify_tier(
            assertion="present",
            context_failed=True,
            terminology_score=1.0,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 3

    def test_absent_assertion_overrides_perfect_score(self):
        d = classify_tier(
            assertion="absent",
            context_failed=False,
            terminology_score=1.0,
            surface_form_status="approved",
            coding_mode="autonomous",
        )
        assert d.tier == 3

    def test_informational_disorder_overrides_perfect_score(self):
        d = classify_tier(
            assertion="present",
            context_failed=False,
            terminology_score=1.0,
            surface_form_status="approved",
            coding_mode="autonomous",
            disorder_verdict="informational",
        )
        assert d.tier == 3
