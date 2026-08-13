"""Unit tests for configurable referral routing guard (P1-E).

Atlas trace:
  DI: DI-34712A9A, DI-B5C78811
  DO: DO-728930A1

Run:
    pytest tests/libs/pipeline/test_referral_routing_guard.py -v
"""
from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# ReferralRoutingGuardRule dataclass
# ---------------------------------------------------------------------------


class TestReferralRoutingGuardRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import PipelineRuleBase, ReferralRoutingGuardRule

        r = ReferralRoutingGuardRule(
            rule_id="rrg-1", pattern="laparoscopy", pattern_type="named_test"
        )
        assert isinstance(r, PipelineRuleBase)
        assert r.pattern == "laparoscopy"
        assert r.pattern_type == "named_test"

    def test_pattern_type_defaults_named_test(self):
        from libs.pipeline.config_types import ReferralRoutingGuardRule

        r = ReferralRoutingGuardRule(rule_id="rrg-2", pattern="test")
        assert r.pattern_type == "named_test"


# ---------------------------------------------------------------------------
# Parity tests: existing patterns still work after refactor
# ---------------------------------------------------------------------------


class TestReferralRoutingGuardParity:
    ROUTING_SPANS = [
        "2WW referral placed",
        "referral submitted",
        "e-referral",
        "two week wait referral submitted",
    ]
    KEEP_SPANS = [
        "FIT positive - 2WW referral submitted",
        "MRI scan arranged",
        "patient declined referral",
        "suspected breast cancer",
    ]

    def _reload(self):
        import libs.ner.referral_routing_guard as g
        with patch.object(g, "_fetch_neo4j_routing_rules", return_value=[]):
            g.reload_referral_routing_guard()

    def test_routing_spans_suppressed(self):
        import libs.ner.referral_routing_guard as g
        self._reload()
        for span in self.ROUTING_SPANS:
            assert g.is_informational_referral_routing(span), (
                f"Expected {span!r} to be identified as routing noise"
            )

    def test_keep_spans_not_suppressed(self):
        import libs.ner.referral_routing_guard as g
        self._reload()
        for span in self.KEEP_SPANS:
            assert not g.is_informational_referral_routing(span), (
                f"Expected {span!r} NOT to be identified as routing noise"
            )


# ---------------------------------------------------------------------------
# Configurable: new named-test patterns added via Neo4j
# ---------------------------------------------------------------------------


class TestReferralRoutingGuardConfigurable:
    def test_custom_named_test_keeps_span(self):
        """A new named test pattern added via Neo4j prevents that span from being dropped."""
        import libs.ner.referral_routing_guard as g

        custom_rule = {
            "rule_id": "rrg-custom-1",
            "pattern": "hysteroscopy",
            "pattern_type": "named_test",
            "active": True,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 10,
        }
        with patch.object(g, "_fetch_neo4j_routing_rules", return_value=[custom_rule]):
            g.reload_referral_routing_guard()
            # A 2WW referral that mentions hysteroscopy should NOT be dropped
            assert not g.is_informational_referral_routing("2WW referral for hysteroscopy")

    def test_inactive_custom_rule_not_applied(self):
        import libs.ner.referral_routing_guard as g

        inactive_rule = {
            "rule_id": "rrg-inactive-1",
            "pattern": "vaginoscopy",
            "pattern_type": "named_test",
            "active": False,
        }
        with patch.object(g, "_fetch_neo4j_routing_rules", return_value=[inactive_rule]):
            g.reload_referral_routing_guard()
            # Without the custom rule, 2WW referral is routing noise
            assert g.is_informational_referral_routing("2WW referral submitted")
