"""Unit tests for configurable terminology concept blocklist (P1-C).

Atlas trace:
  DI: DI-34712A9A
  DO: to be created (terminology.py conversion)

Run:
    pytest tests/libs/pipeline/test_term_concept_blocklist.py -v
"""

from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# TermConceptBlocklistRule dataclass
# ---------------------------------------------------------------------------


class TestTermConceptBlocklistRule:
    def test_extends_pipeline_rule_base(self):
        from libs.pipeline.config_types import (
            PipelineRuleBase,
            TermConceptBlocklistRule,
        )

        r = TermConceptBlocklistRule(
            rule_id="tcb-1",
            surface_form="spinal surgery",
            blocked_concept_ids=["1287097003"],
        )
        assert isinstance(r, PipelineRuleBase)
        assert r.surface_form == "spinal surgery"
        assert "1287097003" in r.blocked_concept_ids

    def test_blocked_concept_ids_defaults_empty(self):
        from libs.pipeline.config_types import TermConceptBlocklistRule

        r = TermConceptBlocklistRule(rule_id="tcb-2", surface_form="test")
        assert r.blocked_concept_ids == []


# ---------------------------------------------------------------------------
# Parity tests: converted module must match original hardcoded behaviour
# ---------------------------------------------------------------------------


class TestIsBlockedMappingParity:
    BLOCKED = [
        ("spinal surgery", "1287097003"),
        ("not sleeping well", "367391008"),
        ("nerve compression", "372063002"),
        ("fit", "91175000"),
        ("allergy, unspecified", "16294009"),
        ("vaseline", "227420009"),
        ("high bmi", "6497000"),
        ("no free fluid", "116176007"),
    ]
    NOT_BLOCKED = [
        ("spinal surgery", "999999999"),
        ("normal text", "1287097003"),
        ("fit", "12345678"),
    ]

    @staticmethod
    def _reload_and_check(text: str, concept_id: str) -> bool:
        from libs.pipeline_graph.subgraphs import terminology as term_mod

        term_mod._reload_blocklist_singleton()
        return term_mod._is_blocked_mapping(text, concept_id)

    def test_blocked_pairs_return_true(self):
        with patch(
            "libs.pipeline_graph.subgraphs.terminology._fetch_neo4j_blocklist",
            return_value=[],
        ):
            for text, cid in self.BLOCKED:
                assert self._reload_and_check(
                    text, cid
                ), f"Expected ({text!r}, {cid!r}) to be blocked"

    def test_non_blocked_pairs_return_false(self):
        with patch(
            "libs.pipeline_graph.subgraphs.terminology._fetch_neo4j_blocklist",
            return_value=[],
        ):
            for text, cid in self.NOT_BLOCKED:
                assert not self._reload_and_check(
                    text, cid
                ), f"Expected ({text!r}, {cid!r}) NOT to be blocked"

    def test_none_concept_id_returns_false(self):
        with patch(
            "libs.pipeline_graph.subgraphs.terminology._fetch_neo4j_blocklist",
            return_value=[],
        ):
            from libs.pipeline_graph.subgraphs import terminology as term_mod

            term_mod._reload_blocklist_singleton()
            assert not term_mod._is_blocked_mapping("spinal surgery", None)


# ---------------------------------------------------------------------------
# Configurable: custom rules via Neo4j
# ---------------------------------------------------------------------------


class TestBlocklistConfigurable:
    def test_custom_rule_blocks_matching_pair(self):
        custom = {
            "rule_id": "custom-1",
            "surface_form": "test phrase",
            "blocked_concept_ids": ["999000001"],
            "active": True,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 50,
        }
        with patch(
            "libs.pipeline_graph.subgraphs.terminology._fetch_neo4j_blocklist",
            return_value=[custom],
        ):
            from libs.pipeline_graph.subgraphs import terminology as term_mod

            term_mod._reload_blocklist_singleton()
            assert term_mod._is_blocked_mapping("test phrase", "999000001")

    def test_inactive_custom_rule_not_applied(self):
        inactive = {
            "rule_id": "inactive-1",
            "surface_form": "inactive phrase",
            "blocked_concept_ids": ["999000002"],
            "active": False,
            "org_id": None,
            "plan_definition_id": None,
            "priority": 50,
        }
        with patch(
            "libs.pipeline_graph.subgraphs.terminology._fetch_neo4j_blocklist",
            return_value=[inactive],
        ):
            from libs.pipeline_graph.subgraphs import terminology as term_mod

            term_mod._reload_blocklist_singleton()
            assert not term_mod._is_blocked_mapping("inactive phrase", "999000002")
