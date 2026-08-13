"""Unit tests for configurable situation lookup normalisation (DO-A8000E51).

Atlas trace:
  DO: DO-A8000E51
  DI: DI-34712A9A

Run:
    pytest tests/libs/pipeline/test_situation_lookup.py -v
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Parity tests: converted module must match original hardcoded behaviour
# ---------------------------------------------------------------------------


class TestSituationLookupParity:
    """All 9 original patterns must produce identical output after conversion."""

    CASES = [
        # (input_text, expected_output)
        ("2ww referral", "fast track referral"),
        ("two week wait referral", "fast track referral"),
        ("on waiting list for colonoscopy", "planned procedure"),
        ("waiting list to have surgery", "planned procedure"),
        ("booked for MRI", "planned procedure"),
        ("booked in for biopsy", "planned procedure"),
        ("scheduled for operation", "planned procedure"),
        ("scheduled to be admitted", "planned procedure"),
        ("planned procedure", "planned procedure"),
        ("planned operation", "planned procedure"),
        ("planned surgery", "planned procedure"),
        ("awaiting procedure", "planned procedure"),
        ("awaiting biopsy", "planned procedure"),
        ("awaiting results", None),
        ("awaiting report", None),
        ("referred for endoscopy", "referral to service"),
        ("referred to specialist", "referral to service"),
        ("referral for urgent assessment", "referral to service"),
        ("referral to colorectal", "referral to service"),
        ("no matching phrase here", None),
        ("", None),
    ]

    @pytest.mark.parametrize("text,expected", CASES)
    def test_parity(self, text: str, expected):
        with patch("libs.ner.context_detector._fetch_neo4j_rules", return_value=[]):
            from libs.ner import context_detector

            context_detector._reload_singleton()
            result = context_detector.normalize_situation_lookup(text)
        assert result == expected, f"text={text!r}: expected {expected!r}, got {result!r}"


# ---------------------------------------------------------------------------
# Configurable rules: new rules injected at runtime take effect
# ---------------------------------------------------------------------------


class TestSituationLookupConfigurable:
    def test_custom_neo4j_rule_takes_effect_after_reload(self):
        """A Neo4j rule added at runtime is used after _reload_singleton()."""
        custom_rule = {
            "rule_id": "test-custom-1",
            "pattern": r"\btest\s+phrase\b",
            "canonical": "test canonical term",
            "active": True,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 50,
            "created_by": "test",
            "created_at": "2026-08-12",
        }
        with patch(
            "libs.ner.context_detector._fetch_neo4j_rules",
            return_value=[custom_rule],
        ):
            from libs.ner import context_detector

            context_detector._reload_singleton()
            result = context_detector.normalize_situation_lookup("test phrase here")
        assert result == "test canonical term"

    def test_inactive_neo4j_rule_not_applied(self):
        """An inactive custom rule does not affect output."""
        inactive_rule = {
            "rule_id": "inactive-1",
            "pattern": r"\bshould\s+not\s+match\b",
            "canonical": "should not appear",
            "active": False,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 50,
            "created_by": "test",
            "created_at": "2026-08-12",
        }
        with patch(
            "libs.ner.context_detector._fetch_neo4j_rules",
            return_value=[inactive_rule],
        ):
            from libs.ner import context_detector

            context_detector._reload_singleton()
            result = context_detector.normalize_situation_lookup(
                "should not match"
            )
        assert result != "should not appear"

    def test_none_canonical_returns_none(self):
        """A rule with canonical=None returns None (pass-through to original text)."""
        none_rule = {
            "rule_id": "none-canonical-1",
            "pattern": r"\bspecial\s+case\b",
            "canonical": None,
            "active": True,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 50,
            "created_by": "test",
            "created_at": "2026-08-12",
        }
        with patch(
            "libs.ner.context_detector._fetch_neo4j_rules",
            return_value=[none_rule],
        ):
            from libs.ner import context_detector

            context_detector._reload_singleton()
            result = context_detector.normalize_situation_lookup("special case here")
        assert result is None


# ---------------------------------------------------------------------------
# SituationLookupRule dataclass
# ---------------------------------------------------------------------------


class TestSituationLookupRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import PipelineRuleBase, SituationLookupRule

        r = SituationLookupRule(rule_id="s-1", pattern=r"\btest\b", canonical="test")
        assert isinstance(r, PipelineRuleBase)
        assert r.pattern == r"\btest\b"
        assert r.canonical == "test"

    def test_canonical_can_be_none(self):
        from libs.pipeline.config_types import SituationLookupRule

        r = SituationLookupRule(rule_id="s-2", pattern=r"\bfoo\b", canonical=None)
        assert r.canonical is None
