"""Unit tests for configurable lab value guard (P1-D).

Atlas trace:
  DI: DI-34712A9A, DI-9456E5BE
  DO: DO-AA3B7FCC

Run:
    pytest tests/libs/pipeline/test_lab_value_guard.py -v
"""
from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# LabValueGuardRule dataclass
# ---------------------------------------------------------------------------


class TestLabValueGuardRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import LabValueGuardRule, PipelineRuleBase

        r = LabValueGuardRule(rule_id="lv-1", pattern=r"cystatin[\s-]*c")
        assert isinstance(r, PipelineRuleBase)
        assert r.pattern == r"cystatin[\s-]*c"

    def test_suppressed_disorders_defaults_empty(self):
        from libs.pipeline.config_types import LabValueGuardRule

        r = LabValueGuardRule(rule_id="lv-2", pattern="test")
        assert r.suppressed_disorders == []


# ---------------------------------------------------------------------------
# Parity tests: builtin patterns still detected after refactor
# ---------------------------------------------------------------------------


class TestLabValueGuardParity:
    BUILTIN_LAB_SENTENCES = [
        "eGFR 58 mL/min",
        "Creatinine 120 umol/L",
        "HbA1c 62 mmol/mol",
        "Haemoglobin 110 g/L",
        "Platelet count 150 10^9/L",
        "Troponin elevated 45 ng/mL",
        "TSH 4.2 mU/L",
        "ALT 45 u/L",
    ]

    def test_builtin_lab_sentences_detected(self):
        import libs.ner.lab_value_guard as guard

        with patch.object(guard, "_fetch_neo4j_lab_rules", return_value=[]):
            guard.reload_lab_value_guard()
            for sentence in self.BUILTIN_LAB_SENTENCES:
                assert guard.is_lab_result_sentence(sentence), (
                    f"Expected {sentence!r} to be detected as a lab result sentence"
                )

    def test_non_lab_sentence_not_detected(self):
        import libs.ner.lab_value_guard as guard

        with patch.object(guard, "_fetch_neo4j_lab_rules", return_value=[]):
            guard.reload_lab_value_guard()
            assert not guard.is_lab_result_sentence("Patient has weight loss and fatigue")


# ---------------------------------------------------------------------------
# Configurable: new lab test patterns added via Neo4j
# ---------------------------------------------------------------------------


class TestLabValueGuardConfigurable:
    def test_custom_pattern_detected_after_reload(self):
        """A new lab test pattern added via Neo4j is detected after reload."""
        import libs.ner.lab_value_guard as guard

        custom_rule = {
            "rule_id": "lv-custom-1",
            "pattern": r"cystatin[\s-]*c",
            "suppressed_disorders": [],
            "active": True,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 10,
        }
        with patch.object(guard, "_fetch_neo4j_lab_rules", return_value=[custom_rule]):
            guard.reload_lab_value_guard()
            assert guard.is_lab_result_sentence("Cystatin C 1.2 mg/L")

    def test_inactive_custom_pattern_not_applied(self):
        """An inactive custom rule does not extend the lab test regex."""
        import libs.ner.lab_value_guard as guard

        inactive_rule = {
            "rule_id": "lv-inactive-1",
            "pattern": r"myoglobin[\s-]*level",
            "suppressed_disorders": [],
            "active": False,
        }
        with patch.object(guard, "_fetch_neo4j_lab_rules", return_value=[inactive_rule]):
            guard.reload_lab_value_guard()
            # Only measurement, no custom lab name -- should not be a lab sentence
            assert not guard.is_lab_result_sentence("myoglobin level 45 ug/L")
