"""AND-of-findings becomes AND(sex, OR(findings)) for NICE OR wording.

Atlas:
  UN-5F3BF083
  DI-8BAC9BB3
  DO-62FE139E
  VT-766B13F8
"""

from __future__ import annotations

from copy import deepcopy

from libs.guidelines.or_wrap_and_findings import or_wrap_and_findings


def _seed(concept_id: str, term: str, tag: str) -> dict:
    return {
        "snomed_concept_id": concept_id,
        "preferred_term": term,
        "semantic_tag": tag,
        "include_descendants": False,
    }


def _finding(
    concept_id: str,
    term: str,
    tag: str,
    source_row_text: str,
) -> dict:
    return {
        "kind": "CONCEPT",
        "criterion": {
            "snomed_concept_id": concept_id,
            "preferred_term": term,
            "semantic_tag": tag,
            "term": "",
            "seeds": [_seed(concept_id, term, tag)],
            "excluded_concept_ids": [],
            "primary_concept_id": concept_id,
            "needs_human_review": False,
        },
        "source_row_text": source_row_text,
    }


def _sex_female() -> dict:
    return {
        "kind": "DEMOGRAPHIC",
        "field": "sex",
        "operator": "=",
        "value": "female",
    }


def _ng12_1517_and_of_three() -> dict:
    return {
        "kind": "AND",
        "children": [
            _sex_female(),
            _finding(
                "289477004",
                "Mass of vulva (finding)",
                "finding",
                "vulval lump,",
            ),
            _finding(
                "68640004",
                "Ulceration of vulva (disorder)",
                "disorder",
                "ulceration",
            ),
            _finding(
                "890094005",
                "Bleeding from genital region (finding)",
                "finding",
                "bleeding.",
            ),
        ],
    }


def test_and_of_three_findings_becomes_and_sex_or_findings() -> None:
    out = or_wrap_and_findings(_ng12_1517_and_of_three())
    assert out["kind"] == "AND"
    assert len(out["children"]) == 2
    assert out["children"][0] == _sex_female()
    or_node = out["children"][1]
    assert or_node["kind"] == "OR"
    ids = [c["criterion"]["snomed_concept_id"] for c in or_node["children"]]
    assert ids == ["289477004", "68640004", "890094005"]


def test_preserves_seeds_and_source_row_text() -> None:
    out = or_wrap_and_findings(_ng12_1517_and_of_three())
    findings = out["children"][1]["children"]
    by_id = {c["criterion"]["snomed_concept_id"]: c for c in findings}
    ulcer = by_id["68640004"]
    assert ulcer["source_row_text"] == "ulceration"
    assert ulcer["criterion"]["seeds"] == [
        _seed("68640004", "Ulceration of vulva (disorder)", "disorder")
    ]
    assert ulcer["criterion"]["seeds"][0]["include_descendants"] is False


def test_already_or_wrapped_tree_is_unchanged() -> None:
    tree = {
        "kind": "AND",
        "children": [
            _sex_female(),
            {
                "kind": "OR",
                "children": [
                    _finding(
                        "68640004",
                        "Ulceration of vulva (disorder)",
                        "disorder",
                        "ulceration",
                    ),
                    _finding(
                        "289477004",
                        "Mass of vulva (finding)",
                        "finding",
                        "vulval lump,",
                    ),
                ],
            },
        ],
    }
    assert or_wrap_and_findings(tree) == tree


def test_does_not_mutate_input() -> None:
    original = _ng12_1517_and_of_three()
    snapshot = deepcopy(original)
    or_wrap_and_findings(original)
    assert original == snapshot


def test_leaves_mixed_group_children_alone() -> None:
    tree = {
        "kind": "AND",
        "children": [
            _sex_female(),
            _finding(
                "68640004",
                "Ulceration of vulva (disorder)",
                "disorder",
                "ulceration",
            ),
            {
                "kind": "AND",
                "children": [
                    _finding(
                        "289477004",
                        "Mass of vulva (finding)",
                        "finding",
                        "vulval lump,",
                    ),
                ],
            },
        ],
    }
    assert or_wrap_and_findings(tree) == tree
