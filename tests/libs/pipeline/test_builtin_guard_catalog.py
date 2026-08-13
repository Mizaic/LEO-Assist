"""Unit tests for the built-in NER guard catalog (read-only Pipeline Guards list).

Run:
    pytest tests/libs/pipeline/test_builtin_guard_catalog.py -v --no-coverage
"""
from __future__ import annotations

from libs.pipeline.builtin_guard_catalog import (
    builtin_rule_ids,
    is_builtin_rule_id,
    list_builtin_guard_rules,
    merge_listed_rules,
)

_FAMILIES = (
    "scope_guard",
    "lab_value_guard",
    "referral_routing_guard",
    "assertion_guard",
    "entity_type_norm",
    "checkbox_norm",
    "situation_lookup",
    "term_concept_blocklist",
)


def test_every_family_has_at_least_one_builtin() -> None:
    rows = list_builtin_guard_rules()
    families = {r["family"] for r in rows}
    for family in _FAMILIES:
        assert family in families, f"missing builtins for {family}"


def test_builtin_rows_are_readonly() -> None:
    rows = list_builtin_guard_rules()
    assert rows, "expected built-in rules"
    for row in rows:
        assert row["source"] == "builtin"
        assert row["readonly"] is True
        assert row["active"] is True
        assert row["rule_id"]
        assert row["pattern"]


def test_family_filter_returns_only_that_family() -> None:
    rows = list_builtin_guard_rules("situation_lookup")
    assert rows
    assert all(r["family"] == "situation_lookup" for r in rows)
    assert any(r["rule_id"] == "sl-001" for r in rows)


def test_situation_seed_and_blocklist_seed_are_listed() -> None:
    ids = builtin_rule_ids()
    assert "sl-001" in ids
    assert "tcb-001" in ids
    assert is_builtin_rule_id("sl-001") is True
    assert is_builtin_rule_id("not-a-real-rule") is False


def test_merge_puts_custom_first_and_skips_overridden_builtin() -> None:
    custom = [
        {
            "rule_id": "sl-001",
            "family": "situation_lookup",
            "pattern": "custom override",
            "rule_type": "situation_lookup",
            "active": True,
        }
    ]
    merged = merge_listed_rules(custom, "situation_lookup")
    assert merged[0]["rule_id"] == "sl-001"
    assert merged[0]["source"] == "custom"
    assert merged[0]["readonly"] is False
    assert merged[0]["pattern"] == "custom override"
    builtin_ids = [r["rule_id"] for r in merged[1:]]
    assert "sl-001" not in builtin_ids
    assert all(r["source"] == "builtin" for r in merged[1:])


def test_json_seed_summary_uses_comment() -> None:
    rows = list_builtin_guard_rules("term_concept_blocklist")
    fit = next(r for r in rows if r["rule_id"] == "tcb-004")
    assert "FIT" in fit["summary"] or "fit" in fit["pattern"].lower()


def test_merge_shows_builtins_when_custom_list_is_empty() -> None:
    merged = merge_listed_rules([], None)
    assert len(merged) == len(list_builtin_guard_rules())
    assert all(r["source"] == "builtin" for r in merged)
