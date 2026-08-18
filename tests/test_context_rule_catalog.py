"""TDD: shipped ConText cues are listed and can be turned off.

Atlas: Knowledge authors can see and turn off shipped pipeline cues.
"""

from __future__ import annotations

from libs.ner.context_rule_catalog import (
    list_packaged_context_rules,
    merge_context_rule_list,
    packaged_rule_id,
    suppressed_literals,
)


def test_ac1_list_includes_to_exclude() -> None:
    """AC1: shipped medspaCy cue 'to exclude' is listed as builtin."""
    rows = list_packaged_context_rules()
    hits = [r for r in rows if r["literal"].lower() == "to exclude"]
    assert hits, "to exclude must appear in the packaged ConText list"
    row = hits[0]
    assert row["source"] == "builtin"
    assert row["category"] == "NEGATED_EXISTENCE"
    assert row["rule_id"] == packaged_rule_id("default", "to exclude")
    assert row["active"] is True


def test_ac1_list_includes_not() -> None:
    rows = list_packaged_context_rules()
    hits = [r for r in rows if r["literal"].lower() == "not"]
    assert hits
    assert hits[0]["source"] == "builtin"


def test_ac2_suppress_marks_default_inactive() -> None:
    """AC2: a suppress row marks the shipped cue inactive in the list."""
    packaged = list_packaged_context_rules()
    custom = [
        {
            "rule_id": packaged_rule_id("default", "to exclude"),
            "literal": "to exclude",
            "category": "NEGATED_EXISTENCE",
            "active": False,
            "source": "custom",
        }
    ]
    merged = merge_context_rule_list(packaged, custom)
    hits = [r for r in merged if r["literal"].lower() == "to exclude"]
    assert len(hits) == 1
    assert hits[0]["active"] is False
    assert hits[0]["source"] == "builtin"


def test_ac2_suppressed_literals_from_inactive_rows() -> None:
    rows = [
        {"literal": "to exclude", "active": False, "rule_id": "default:to exclude"},
        {"literal": "pmhx", "active": True, "rule_id": "abc"},
    ]
    assert suppressed_literals(rows) == {"to exclude"}
