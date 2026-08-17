"""Fact-link runtime allowlist.

Atlas trace:
  VT: VT-A514931C
  DI: DI-6ACD24D2
  DO: DO-8E641A9E

Run:
    pytest tests/libs/pipeline/test_fact_link_guard.py -v --no-coverage
"""

from __future__ import annotations

from unittest.mock import patch


def _reload(custom: list[dict] | None = None):
    from libs.relations import policy

    with patch.object(policy, "_fetch_fact_link_rows", return_value=custom or []):
        policy.reload_fact_link_guard()
    return policy


def test_default_runtime_types() -> None:
    policy = _reload()
    types = policy.allowed_relation_types()
    assert {
        "finding_site",
        "interprets",
        "component_of",
        "causative_agent",
    } <= types
    assert "associated_finding" not in types
    assert "qualifies" not in types


def test_causative_agent_allowed_for_allergy() -> None:
    policy = _reload()
    allowed, _ = policy.is_relation_allowed(
        source_label="situation",
        target_label="substance",
        relation_type="causative_agent",
    )
    assert allowed


def test_custom_relation_type_after_reload() -> None:
    policy = _reload(
        [
            {
                "rule_id": "fl-custom",
                "rule_type": "allowed_relation",
                "pattern": "qualifies",
                "active": True,
            }
        ]
    )
    assert "qualifies" in policy.allowed_relation_types()


def test_policy_types_still_include_historic_gold() -> None:
    policy = _reload()
    historic = policy.policy_relation_types()
    assert "qualifies" in historic
    assert "associated_finding" in historic
    assert "causative_agent" in historic
