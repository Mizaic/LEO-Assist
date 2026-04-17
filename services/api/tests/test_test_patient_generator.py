"""Tests for the synthetic test-patient generator -- VT-LEO-AI-165.

Covers:
  - happy + fail proposal pair for a simple AND rule.
  - branch proposals at boundary_plus_pairs depth (top-level OR).
  - boundary proposals for age DEMOGRAPHIC nodes.
  - dedup_existing skips proposals whose hash already exists.
  - scope_type='all' selects every active rule.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services import test_patient_generator as gen


def _concept(node_id: str, cid: str) -> dict:
    return {
        "node_id": node_id,
        "kind": "CONCEPT",
        "criterion": {"snomed_concept_id": cid},
    }


def _rule(rule_id: str, tree: dict, guideline_id: str = "g1") -> dict:
    return {
        "rule_id": rule_id,
        "name": f"Rule {rule_id}",
        "guideline_id": guideline_id,
        "logic_json": json.dumps(tree),
    }


# -- happy + fail ----------------------------------------------------------


def test_generates_happy_and_fail_for_simple_and(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(
        "r1",
        {
            "node_id": "root",
            "kind": "AND",
            "children": [_concept("c1", "100"), _concept("c2", "200")],
        },
    )
    monkeypatch.setattr(gen, "list_rules_in_scope", lambda *a, **k: [rule])

    result = gen.generate(
        MagicMock(),
        scope_type="rule",
        guideline_id=None,
        rule_id="r1",
        branch_node_id=None,
        depth="minimal_pair",
        exclude_existing=False,
    )

    kinds = {p["kind"] for p in result["proposals"]}
    assert kinds == {"happy", "fail"}
    happy = next(p for p in result["proposals"] if p["kind"] == "happy")
    fail = next(p for p in result["proposals"] if p["kind"] == "fail")
    assert sorted(happy["patient"]["codes"]) == ["100", "200"]
    # fail should drop one code
    assert len(fail["patient"]["codes"]) == 1


# -- branch + boundary -----------------------------------------------------


def test_branch_and_boundary_at_full_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(
        "r1",
        {
            "node_id": "root",
            "kind": "AND",
            "children": [
                {
                    "node_id": "or1",
                    "kind": "OR",
                    "children": [_concept("a", "1"), _concept("b", "2")],
                },
                {
                    "node_id": "age",
                    "kind": "DEMOGRAPHIC",
                    "field": "age",
                    "operator": ">=",
                    "value": 65,
                },
            ],
        },
    )
    monkeypatch.setattr(gen, "list_rules_in_scope", lambda *a, **k: [rule])

    result = gen.generate(
        MagicMock(),
        scope_type="guideline",
        guideline_id="g1",
        rule_id=None,
        branch_node_id=None,
        depth="boundary_plus_pairs",
        exclude_existing=False,
    )

    kinds = [p["kind"] for p in result["proposals"]]
    # one happy, one fail, two branch (a and b), and >=2 boundary
    assert "branch" in kinds
    assert "boundary" in kinds
    branches = [p for p in result["proposals"] if p["kind"] == "branch"]
    assert len(branches) == 2
    boundary = [p for p in result["proposals"] if p["kind"] == "boundary"]
    boundary_ages = sorted({float(p["patient"]["age"]) for p in boundary})
    # at boundary (65) and just below (64)
    assert 65.0 in boundary_ages and 64.0 in boundary_ages


def test_exclude_existing_drops_known_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule(
        "r1",
        {"node_id": "root", "kind": "AND", "children": [_concept("c1", "100")]},
    )
    monkeypatch.setattr(gen, "list_rules_in_scope", lambda *a, **k: [rule])
    # Pretend every proposal already exists.
    monkeypatch.setattr(gen, "find_existing", lambda *a, **k: "tp_existing")

    result = gen.generate(
        MagicMock(),
        scope_type="rule",
        guideline_id="g1",
        rule_id="r1",
        branch_node_id=None,
        depth="minimal_pair",
        exclude_existing=True,
    )
    assert result["proposals"] == []


def test_scope_type_all_pulls_every_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_list(client, **kwargs):  # noqa: ARG001
        captured.update(kwargs)
        return []

    monkeypatch.setattr(gen, "list_rules_in_scope", fake_list)

    gen.generate(
        MagicMock(),
        scope_type="all",
        guideline_id=None,
        rule_id=None,
        branch_node_id=None,
        depth="minimal_pair",
        exclude_existing=False,
    )
    # 'all' must not pin to a specific guideline_id or rule_id
    assert captured == {}
