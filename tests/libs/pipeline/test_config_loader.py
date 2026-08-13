"""Unit tests for the three-tier NER guard rule config loader (VT-DE336BEB).

Atlas trace:
  VT: VT-DE336BEB
  DI: DI-34712A9A
  DO: DO-F20DE29D

Run:
    pytest tests/libs/pipeline/test_config_loader.py -v --no-coverage
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from libs.pipeline.config_types import PipelineRuleBase
from libs.pipeline.config_loader import load_rules


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_path(tmp_path: Path) -> Path:
    data = {
        "rules": [
            {"rule_id": "builtin-1", "pattern": "weight loss", "action": "suppress"},
            {"rule_id": "builtin-2", "pattern": "haematuria", "action": "suppress"},
        ]
    }
    p = tmp_path / "test_rules.json"
    p.write_text(json.dumps(data))
    return p


def _neo4j_row(
    rule_id: str,
    org_id,
    plan_id=None,
    active: bool = True,
    priority: int = 10,
) -> dict:
    return {
        "rule_id": rule_id,
        "pattern": f"pattern-{rule_id}",
        "action": "suppress",
        "org_id": org_id,
        "plan_definition_id": plan_id,
        "active": active,
        "priority": priority,
        "created_by": "test@example.com",
        "created_at": "2026-08-12",
    }


# ---------------------------------------------------------------------------
# PipelineRuleBase
# ---------------------------------------------------------------------------


class TestPipelineRuleBase:
    def test_all_required_fields_present(self):
        r = PipelineRuleBase(
            rule_id="r-1",
            active=True,
            org_id=None,
            plan_definition_id=None,
            priority=10,
            created_by="test",
            created_at="2026-01-01",
            source="builtin",
        )
        assert r.rule_id == "r-1"
        assert r.source == "builtin"
        assert r.active is True

    def test_defaults_are_sane(self):
        r = PipelineRuleBase(rule_id="r-2")
        assert r.active is True
        assert r.source == "builtin"
        assert r.org_id is None
        assert r.priority == 10


# ---------------------------------------------------------------------------
# Builtin-only (no Neo4j rows)
# ---------------------------------------------------------------------------


class TestLoadRulesBuiltinOnly:
    def test_builtin_rules_from_seed(self, seed_path: Path):
        """AC1: load_rules with no Neo4j rows returns only seed rules tagged source=builtin."""
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=seed_path)

        assert len(rules) == 2
        assert all(r.source == "builtin" for r in rules)
        ids = {r.rule_id for r in rules}
        assert ids == {"builtin-1", "builtin-2"}

    def test_missing_seed_returns_empty(self, tmp_path: Path):
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=tmp_path / "nope.json")
        assert rules == []


# ---------------------------------------------------------------------------
# Platform-admin rules (org_id IS NULL in Neo4j)
# ---------------------------------------------------------------------------


class TestPlatformAdminRules:
    def test_platform_admin_rule_merged_with_builtins(self, seed_path: Path):
        """AC2: platform-admin rule (org_id=None) is included for all callers."""
        admin_rule = _neo4j_row("admin-1", org_id=None)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[admin_rule]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=seed_path)

        ids = {r.rule_id for r in rules}
        assert "admin-1" in ids
        assert "builtin-1" in ids

    def test_platform_admin_rule_source_is_custom(self, seed_path: Path):
        admin_rule = _neo4j_row("admin-1", org_id=None)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[admin_rule]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=seed_path)

        admin = next(r for r in rules if r.rule_id == "admin-1")
        assert admin.source == "custom"


# ---------------------------------------------------------------------------
# Tenant scoping
# ---------------------------------------------------------------------------


class TestTenantScoping:
    def test_tenant_rule_included_for_matching_org(self, seed_path: Path):
        """AC2: tenant rule (org_id=org-A) included for org-A callers."""
        tenant_rule = _neo4j_row("tenant-1", org_id="org-A")
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[tenant_rule]):
            rules = load_rules("test", org_id="org-A", plan_id=None, seed_path=seed_path)

        assert any(r.rule_id == "tenant-1" for r in rules)

    def test_tenant_rule_excluded_for_different_org(self, seed_path: Path):
        """AC2: tenant rule (org_id=org-A) excluded for org-B callers."""
        tenant_rule = _neo4j_row("tenant-1", org_id="org-A")
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[tenant_rule]):
            rules = load_rules("test", org_id="org-B", plan_id=None, seed_path=seed_path)

        assert not any(r.rule_id == "tenant-1" for r in rules)


# ---------------------------------------------------------------------------
# Inactive rule exclusion
# ---------------------------------------------------------------------------


class TestInactiveRuleExclusion:
    def test_inactive_neo4j_rule_excluded(self, seed_path: Path):
        """AC3: rule with active=False is excluded regardless of scope."""
        inactive = _neo4j_row("inactive-1", org_id=None, active=False)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[inactive]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=seed_path)

        assert not any(r.rule_id == "inactive-1" for r in rules)

    def test_active_neo4j_rule_included(self, seed_path: Path):
        active = _neo4j_row("active-1", org_id=None, active=True)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[active]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=seed_path)

        assert any(r.rule_id == "active-1" for r in rules)


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    def test_higher_priority_rules_come_first(self, seed_path: Path):
        """AC4: rules sorted by priority descending."""
        low = _neo4j_row("low-p", org_id=None, priority=1)
        high = _neo4j_row("high-p", org_id=None, priority=100)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[low, high]):
            rules = load_rules("test", org_id=None, plan_id=None, seed_path=seed_path)

        custom = [r for r in rules if r.source == "custom"]
        assert custom[0].rule_id == "high-p"
        assert custom[1].rule_id == "low-p"

    def test_workflow_rule_included_when_plan_matches(self, seed_path: Path):
        """Workflow rule (plan_id=plan-X) included when plan_id matches."""
        wf_rule = _neo4j_row("wf-1", org_id="org-A", plan_id="plan-X", priority=50)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[wf_rule]):
            rules = load_rules("test", org_id="org-A", plan_id="plan-X", seed_path=seed_path)

        assert any(r.rule_id == "wf-1" for r in rules)

    def test_workflow_rule_excluded_when_plan_does_not_match(self, seed_path: Path):
        wf_rule = _neo4j_row("wf-1", org_id="org-A", plan_id="plan-X", priority=50)
        with patch("libs.pipeline.config_loader._fetch_neo4j_rules", return_value=[wf_rule]):
            rules = load_rules("test", org_id="org-A", plan_id="plan-Y", seed_path=seed_path)

        assert not any(r.rule_id == "wf-1" for r in rules)


# ---------------------------------------------------------------------------
# Guard rule Cypher strings sanity check
# ---------------------------------------------------------------------------


class TestGuardRuleCypher:
    def test_get_rules_by_family_contains_merge_pattern(self):
        """AC5: GET_RULES_BY_FAMILY queries on family."""
        from libs.cypher.guard_rule_queries import GET_RULES_BY_FAMILY

        assert "$family" in GET_RULES_BY_FAMILY
        assert "NerGuardRule" in GET_RULES_BY_FAMILY

    def test_upsert_rule_merges_on_rule_id(self):
        from libs.cypher.guard_rule_queries import UPSERT_RULE

        assert "MERGE" in UPSERT_RULE
        assert "$rule_id" in UPSERT_RULE

    def test_deactivate_rule_sets_active_false(self):
        from libs.cypher.guard_rule_queries import DEACTIVATE_RULE

        assert "active" in DEACTIVATE_RULE.lower()
        assert "$rule_id" in DEACTIVATE_RULE
