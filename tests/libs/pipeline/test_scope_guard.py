"""P1-G TDD tests -- scope guard configurable extension.

Tests:
- ScopeGuardRule dataclass exists and extends PipelineRuleBase
- is_safety_netting_sentence parity for built-in patterns
- Custom safety-netting patterns added via Neo4j are recognised
- Inactive custom rules are ignored
"""
from __future__ import annotations

from unittest.mock import patch


class TestScopeGuardRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import PipelineRuleBase, ScopeGuardRule

        r = ScopeGuardRule()
        assert isinstance(r, PipelineRuleBase)

    def test_rule_type_defaults_safety_netting(self):
        from libs.pipeline.config_types import ScopeGuardRule

        r = ScopeGuardRule()
        assert r.rule_type == "safety_netting"

    def test_pattern_field(self):
        from libs.pipeline.config_types import ScopeGuardRule

        r = ScopeGuardRule(pattern=r"dial\s+999")
        assert r.pattern == r"dial\s+999"


class TestScopeGuardParity:
    _SAFETY_SENTENCES = [
        "If you develop chest pain, call 999 immediately.",
        "Please call 111 if symptoms worsen.",
        "Attend A&E if you feel faint or collapse.",
        "Go to hospital if the bleeding does not stop.",
        "Return immediately if you develop a high fever.",
    ]

    _CLINICAL_SENTENCES = [
        "Patient has a 3-week history of weight loss.",
        "Referred for urgent colonoscopy.",
        "Background of hypertension and type 2 diabetes.",
    ]

    def test_builtin_patterns_detected(self):
        from libs.ner.scope_guard import is_safety_netting_sentence

        for sent in self._SAFETY_SENTENCES:
            assert is_safety_netting_sentence(sent), (
                f"Expected safety-netting match: {sent!r}"
            )

    def test_clinical_sentences_not_flagged(self):
        from libs.ner.scope_guard import is_safety_netting_sentence

        for sent in self._CLINICAL_SENTENCES:
            assert not is_safety_netting_sentence(sent), (
                f"Expected NO safety-netting match: {sent!r}"
            )


class TestScopeGuardConfigurable:
    def test_custom_safety_netting_pattern_detected(self):
        from libs.ner.scope_guard import (
            is_safety_netting_sentence,
            reload_scope_guard,
        )

        fake_row = {
            "rule_id": "test-sg-001",
            "active": True,
            "payload": '{"pattern": "dial\\\\s+999", "rule_type": "safety_netting"}',
            "family": "scope_guard",
        }

        with patch(
            "libs.ner.scope_guard._fetch_neo4j_scope_rules",
            return_value=[fake_row],
        ):
            reload_scope_guard()

        assert is_safety_netting_sentence("Please dial 999 for any concerns.")

    def test_inactive_custom_rule_not_applied(self):
        from libs.ner.scope_guard import (
            is_safety_netting_sentence,
            reload_scope_guard,
        )

        fake_row = {
            "rule_id": "test-sg-inactive",
            "active": False,
            "payload": '{"pattern": "dial\\\\s+999", "rule_type": "safety_netting"}',
            "family": "scope_guard",
        }

        with patch(
            "libs.ner.scope_guard._fetch_neo4j_scope_rules",
            return_value=[fake_row],
        ):
            reload_scope_guard()

        # "dial 999" is not a built-in pattern; should not be matched
        assert not is_safety_netting_sentence("Please dial 999 for any concerns.")
