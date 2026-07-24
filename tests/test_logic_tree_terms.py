"""Tests for libs.guidance.logic_tree_terms.

Atlas trace: DO-BE96444E / DI-BAC284B4
"""

from __future__ import annotations

from libs.guidance.logic_tree_terms import (
    concept_terms,
    normalise_concept_term,
    parse_logic_json,
    walk_concept_criteria,
)


class TestNormaliseConceptTerm:
    def test_strips_trailing_semantic_tag(self):
        assert normalise_concept_term("Vomiting (finding)") == "vomiting"

    def test_lowercases_and_collapses_whitespace(self):
        assert (
            normalise_concept_term("Upper   Abdominal Pain") == "upper abdominal pain"
        )

    def test_strips_punctuation(self):
        assert normalise_concept_term("nausea, vomiting") == "nausea vomiting"

    def test_none_and_empty_return_empty_string(self):
        assert normalise_concept_term(None) == ""
        assert normalise_concept_term("") == ""
        assert normalise_concept_term("   ") == ""


class TestParseLogicJson:
    def test_accepts_dict_unchanged(self):
        tree = {"kind": "AND", "children": []}
        assert parse_logic_json(tree) is tree

    def test_parses_json_string(self):
        assert parse_logic_json('{"kind": "AND", "children": []}') == {
            "kind": "AND",
            "children": [],
        }

    def test_returns_none_for_garbage(self):
        assert parse_logic_json("not json") is None
        assert parse_logic_json(None) is None
        assert parse_logic_json(42) is None
        assert parse_logic_json("[]") is None  # valid JSON, not a dict


class TestWalkConceptCriteria:
    def test_bare_concept_leaf(self):
        criterion = {
            "snomed_concept_id": "49727002",
            "preferred_term": "Cough (finding)",
        }
        node = {"kind": "concept", "criterion": criterion}
        assert walk_concept_criteria(node) == [criterion]

    def test_recurses_into_nested_groups(self):
        vomiting = {"snomed_concept_id": "422587007", "preferred_term": "Nausea"}
        nausea = {"snomed_concept_id": "422400008", "preferred_term": "Vomiting"}
        tree = {
            "kind": "AND",
            "children": [
                {
                    "kind": "OR",
                    "children": [
                        {"kind": "concept", "criterion": vomiting},
                        {"kind": "concept", "criterion": nausea},
                    ],
                },
                {"kind": "demographic", "field": "age", "operator": ">=", "value": 55},
            ],
        }
        found = walk_concept_criteria(tree)
        assert found == [vomiting, nausea]

    def test_skips_concept_leaf_missing_snomed_id(self):
        node = {"kind": "concept", "criterion": {"preferred_term": "Vague phrase"}}
        assert walk_concept_criteria(node) == []

    def test_tolerant_of_non_dict_input(self):
        assert walk_concept_criteria(None) == []
        assert walk_concept_criteria("not a tree") == []
        assert walk_concept_criteria([]) == []


class TestConceptTerms:
    def test_returns_both_free_text_and_preferred_term(self):
        criterion = {
            "snomed_concept_id": "422587007",
            "term": "being sick",
            "preferred_term": "Vomiting (finding)",
        }
        assert concept_terms(criterion) == {"being sick", "vomiting"}

    def test_dedupes_when_term_and_preferred_term_normalise_the_same(self):
        criterion = {
            "snomed_concept_id": "422587007",
            "term": "vomiting",
            "preferred_term": "Vomiting (finding)",
        }
        assert concept_terms(criterion) == {"vomiting"}

    def test_handles_missing_fields(self):
        assert concept_terms({"snomed_concept_id": "1"}) == set()
