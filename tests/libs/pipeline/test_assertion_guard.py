"""P1-F TDD tests -- assertion guard configurable extension.

Tests:
- AssertionGuardRule dataclass is present and extends PipelineRuleBase
- fix_lifestyle_status_assertions parity for existing built-in concepts
- Custom concept IDs added via Neo4j are respected
- Inactive custom rules are ignored
"""
from __future__ import annotations

from unittest.mock import patch


# -- Dataclass contract -------------------------------------------------------


class TestAssertionGuardRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import AssertionGuardRule, PipelineRuleBase

        r = AssertionGuardRule()
        assert isinstance(r, PipelineRuleBase)

    def test_rule_type_defaults_lifestyle_concept(self):
        from libs.pipeline.config_types import AssertionGuardRule

        r = AssertionGuardRule()
        assert r.rule_type == "lifestyle_concept"

    def test_concept_id_field(self):
        from libs.pipeline.config_types import AssertionGuardRule

        r = AssertionGuardRule(concept_id="8517006")
        assert r.concept_id == "8517006"


# -- Parity: built-in concept IDs are preserved -------------------------------


class TestAssertionGuardParity:
    _BUILTINS = [
        ("8517006", "Ex-smoker"),
        ("266919005", "Never smoked tobacco"),
        ("8392000", "Non-smoker"),
    ]

    def test_builtin_concepts_restored_to_present(self):
        from libs.pipeline.post_processing import fix_lifestyle_status_assertions

        for concept_id, label in self._BUILTINS:
            ent = {
                "concept_id": concept_id,
                "term": label,
                "assertion": "absent",
                "semantic_tag": "finding",
            }
            fix_lifestyle_status_assertions([ent])
            assert ent["assertion"] == "present", (
                f"concept {concept_id} ({label}) should be restored to present"
            )

    def test_unrelated_concept_not_changed(self):
        from libs.pipeline.post_processing import fix_lifestyle_status_assertions

        ent = {
            "concept_id": "73211009",
            "term": "Diabetes mellitus",
            "assertion": "absent",
            "semantic_tag": "disorder",
        }
        fix_lifestyle_status_assertions([ent])
        assert ent["assertion"] == "absent"


# -- Configurable: custom concept IDs via Neo4j -------------------------------


class TestAssertionGuardConfigurable:
    def test_custom_concept_restores_present(self):
        from libs.pipeline.post_processing import (
            fix_lifestyle_status_assertions,
            reload_lifestyle_status_guard,
        )

        fake_row = {
            "rule_id": "test-custom-001",
            "active": True,
            "payload": '{"concept_id": "160603005"}',
            "family": "assertion_guard",
        }

        with patch(
            "libs.pipeline.post_processing._fetch_neo4j_assertion_rules",
            return_value=[fake_row],
        ):
            reload_lifestyle_status_guard()

        ent = {
            "concept_id": "160603005",
            "term": "Light drinker",
            "assertion": "absent",
        }
        fix_lifestyle_status_assertions([ent])
        assert ent["assertion"] == "present"

    def test_inactive_custom_rule_ignored(self):
        from libs.pipeline.post_processing import (
            fix_lifestyle_status_assertions,
            reload_lifestyle_status_guard,
        )

        fake_row = {
            "rule_id": "test-inactive-001",
            "active": False,
            "payload": '{"concept_id": "160603005"}',
            "family": "assertion_guard",
        }

        with patch(
            "libs.pipeline.post_processing._fetch_neo4j_assertion_rules",
            return_value=[fake_row],
        ):
            reload_lifestyle_status_guard()

        ent = {
            "concept_id": "160603005",
            "term": "Light drinker",
            "assertion": "absent",
        }
        fix_lifestyle_status_assertions([ent])
        assert ent["assertion"] == "absent"
