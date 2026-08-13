"""P1-I TDD tests -- checkbox normalizer configurable extension.

Tests:
- CheckboxNormRule dataclass exists and extends PipelineRuleBase
- normalize_form_checkbox_text parity: built-in admin questions are suppressed
- Custom admin question patterns added via Neo4j are suppressed
- Inactive custom rules are ignored
"""
from __future__ import annotations

from unittest.mock import patch


class TestCheckboxNormRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import CheckboxNormRule, PipelineRuleBase

        r = CheckboxNormRule()
        assert isinstance(r, PipelineRuleBase)

    def test_rule_type_defaults_admin_question(self):
        from libs.pipeline.config_types import CheckboxNormRule

        r = CheckboxNormRule()
        assert r.rule_type == "admin_question"

    def test_pattern_field(self):
        from libs.pipeline.config_types import CheckboxNormRule

        r = CheckboxNormRule(pattern="does the patient")
        assert r.pattern == "does the patient"


class TestCheckboxNormParity:
    def test_builtin_admin_questions_suppressed(self):
        from libs.ner.form_checkbox_normalizer import normalize_form_checkbox_text

        for phrase in ("Has the patient", "Please confirm", "Is the patient"):
            text = f"{phrase} been seen before? [X]"
            result = normalize_form_checkbox_text(text)
            assert "[NON_EXTRACTABLE]" in result or phrase not in result, (
                f"Expected admin phrase suppressed: {phrase!r}"
            )


class TestCheckboxNormConfigurable:
    def test_custom_admin_question_suppressed(self):
        from libs.ner.form_checkbox_normalizer import (
            normalize_form_checkbox_text,
            reload_checkbox_norm,
        )

        fake_row = {
            "rule_id": "test-cb-001",
            "active": True,
            "payload": '{"pattern": "Does the referrer", "rule_type": "admin_question"}',
            "family": "checkbox_norm",
        }

        with patch(
            "libs.ner.form_checkbox_normalizer._fetch_neo4j_checkbox_rules",
            return_value=[fake_row],
        ):
            reload_checkbox_norm()

        text = "Does the referrer have consent? [X]"
        result = normalize_form_checkbox_text(text)
        assert "[NON_EXTRACTABLE]" in result or "Does the referrer" not in result

    def test_inactive_custom_rule_not_applied(self):
        from libs.ner.form_checkbox_normalizer import (
            normalize_form_checkbox_text,
            reload_checkbox_norm,
        )

        fake_row = {
            "rule_id": "test-cb-inactive",
            "active": False,
            "payload": '{"pattern": "Does the referrer", "rule_type": "admin_question"}',
            "family": "checkbox_norm",
        }

        with patch(
            "libs.ner.form_checkbox_normalizer._fetch_neo4j_checkbox_rules",
            return_value=[fake_row],
        ):
            reload_checkbox_norm()

        text = "Does the referrer have consent? [X]"
        result = normalize_form_checkbox_text(text)
        # Without the custom rule, phrase is not suppressed as NON_EXTRACTABLE
        # (it may or may not be a checkbox line, but it won't be admin-suppressed)
        assert "[NON_EXTRACTABLE]" not in result
