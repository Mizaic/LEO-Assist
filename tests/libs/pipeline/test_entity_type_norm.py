"""P1-H TDD tests -- entity-type normalisation configurable extension.

Tests:
- EntityTypeNormRule dataclass exists and extends PipelineRuleBase
- normalise_entity_types parity for built-in episode marker + severity texts
- Custom texts added via Neo4j are respected
- Inactive custom rules are ignored
"""
from __future__ import annotations

from unittest.mock import patch


class TestEntityTypeNormRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import EntityTypeNormRule, PipelineRuleBase

        r = EntityTypeNormRule()
        assert isinstance(r, PipelineRuleBase)

    def test_rule_type_defaults_episode_marker(self):
        from libs.pipeline.config_types import EntityTypeNormRule

        r = EntityTypeNormRule()
        assert r.rule_type == "episode_marker"

    def test_text_field(self):
        from libs.pipeline.config_types import EntityTypeNormRule

        r = EntityTypeNormRule(text="repeat episode")
        assert r.text == "repeat episode"


class TestEntityTypeNormParity:
    def test_builtin_episode_markers_reclassified(self):
        from libs.pipeline.post_processing import normalise_entity_types

        for marker in ("new episode", "ongoing episode", "first episode"):
            ent = {"label": "X_TEMPORAL", "text": marker}
            normalise_entity_types([ent])
            assert ent["label"] == "qualifier_value", (
                f"Expected qualifier_value for marker {marker!r}"
            )

    def test_builtin_severity_modifiers_reclassified(self):
        from libs.pipeline.post_processing import normalise_entity_types

        for word in ("severe", "mild", "moderate"):
            ent = {"label": "finding", "text": word}
            normalise_entity_types([ent])
            assert ent["label"] == "qualifier_value", (
                f"Expected qualifier_value for severity word {word!r}"
            )


class TestEntityTypeNormConfigurable:
    def test_custom_episode_marker_reclassified(self):
        from libs.pipeline.post_processing import (
            normalise_entity_types,
            reload_entity_type_norm,
        )

        fake_row = {
            "rule_id": "test-etn-001",
            "active": True,
            "payload": '{"text": "repeat episode", "rule_type": "episode_marker"}',
            "family": "entity_type_norm",
        }

        with patch(
            "libs.pipeline.post_processing._fetch_neo4j_entity_norm_rules",
            return_value=[fake_row],
        ):
            reload_entity_type_norm()

        ent = {"label": "X_TEMPORAL", "text": "repeat episode"}
        normalise_entity_types([ent])
        assert ent["label"] == "qualifier_value"

    def test_inactive_custom_rule_ignored(self):
        from libs.pipeline.post_processing import (
            normalise_entity_types,
            reload_entity_type_norm,
        )

        fake_row = {
            "rule_id": "test-etn-inactive",
            "active": False,
            "payload": '{"text": "repeat episode", "rule_type": "episode_marker"}',
            "family": "entity_type_norm",
        }

        with patch(
            "libs.pipeline.post_processing._fetch_neo4j_entity_norm_rules",
            return_value=[fake_row],
        ):
            reload_entity_type_norm()

        ent = {"label": "X_TEMPORAL", "text": "repeat episode"}
        normalise_entity_types([ent])
        assert ent["label"] == "X_TEMPORAL"
