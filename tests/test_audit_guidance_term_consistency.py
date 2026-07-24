"""Unit tests for the periodic term-conflict audit backstop.

Pure logic only (`_index_terms` / `_find_conflicts`) -- no Neo4j, no
filesystem writes. See ``scripts/audit_guidance_term_consistency.py``.
"""

from __future__ import annotations

import json

from scripts.audit_guidance_term_consistency import _find_conflicts, _index_terms


def _rule(rule_id: str, criteria: list[dict]) -> dict:
    tree = {
        "kind": "group",
        "operator": "AND",
        "children": [
            {"kind": "concept", "criterion": criterion} for criterion in criteria
        ],
    }
    return {"rule_id": rule_id, "logic_json": json.dumps(tree)}


def _criterion(term: str, concept_id: str, preferred_term: str | None = None) -> dict:
    return {
        "term": term,
        "snomed_concept_id": concept_id,
        "preferred_term": preferred_term or term,
    }


def test_index_terms_groups_by_normalised_term_and_concept():
    rules = [
        _rule("r1", [_criterion("vomiting", "300359004", "Vomiting (finding)")]),
        _rule("r2", [_criterion("Vomiting", "300359004", "Vomiting (finding)")]),
    ]
    index = _index_terms(rules)
    assert "vomiting" in index
    assert index["vomiting"]["300359004"]["count"] == 2
    assert set(index["vomiting"]["300359004"]["rule_ids"]) == {"r1", "r2"}


def test_index_terms_skips_rules_with_unparsable_logic_json():
    rules = [
        {"rule_id": "r1", "logic_json": "not json"},
        {"rule_id": "r2", "logic_json": None},
    ]
    assert _index_terms(rules) == {}


def test_find_conflicts_flags_terms_mapped_to_more_than_one_concept():
    rules = [
        _rule("r1", [_criterion("nausea", "422587007", "Nausea (finding)")]),
        _rule(
            "r2", [_criterion("nausea", "16932000", "Nausea and vomiting (disorder)")]
        ),
    ]
    index = _index_terms(rules)
    conflicts = _find_conflicts(index, min_count=1)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["term"] == "nausea"
    assert conflict["concept_count"] == 2
    ids = {c["snomed_concept_id"] for c in conflict["concepts"]}
    assert ids == {"422587007", "16932000"}


def test_find_conflicts_ignores_terms_resolved_consistently():
    rules = [
        _rule("r1", [_criterion("weight loss", "89362005")]),
        _rule("r2", [_criterion("weight loss", "89362005")]),
    ]
    index = _index_terms(rules)
    assert _find_conflicts(index, min_count=1) == []


def test_find_conflicts_respects_min_count_threshold():
    rules = [
        _rule("r1", [_criterion("dyspepsia", "16932000")]),
        _rule("r2", [_criterion("dyspepsia", "16932000")]),
        _rule("r3", [_criterion("dyspepsia", "271681002")]),
    ]
    index = _index_terms(rules)
    assert _find_conflicts(index, min_count=1) != []
    assert _find_conflicts(index, min_count=2) == []


def test_find_conflicts_sorted_by_total_occurrences_descending():
    rules = [
        _rule("r1", [_criterion("reflux", "concept-a")]),
        _rule("r2", [_criterion("reflux", "concept-b")]),
        _rule("r3", [_criterion("bloating", "concept-c")]),
        _rule("r4", [_criterion("bloating", "concept-d")]),
        _rule("r5", [_criterion("bloating", "concept-d")]),
    ]
    index = _index_terms(rules)
    conflicts = _find_conflicts(index, min_count=1)
    assert [c["term"] for c in conflicts] == ["bloating", "reflux"]
