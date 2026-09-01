"""NG12 1.5.13 discharge arm is first time OR platelets OR haematuria.

Atlas: UN-5F3BF083, DI-8BAC9BB3, DI-DE8B125E, VT-9CEA9081
"""

from __future__ import annotations

from copy import deepcopy

from libs.guidelines.ng12_1513_discharge import reshape_1513_discharge_or
from services.api.app.services.guidance_rule_edit import LogicNode, validate_logic_tree


def _concept(concept_id: str, term: str, source: str, **extra: object) -> dict:
    criterion: dict = {
        "snomed_concept_id": concept_id,
        "preferred_term": term,
        "semantic_tag": "finding",
        "seeds": [
            {
                "snomed_concept_id": concept_id,
                "preferred_term": term,
                "semantic_tag": "finding",
                "include_descendants": False,
            }
        ],
        "primary_concept_id": concept_id,
    }
    if extra:
        criterion.update(extra)
    return {
        "kind": "CONCEPT",
        "criterion": criterion,
        "source_row_text": source,
    }


def _and_discharge_with_platelets() -> dict:
    return {
        "kind": "AND",
        "children": [
            {
                "kind": "DEMOGRAPHIC",
                "field": "age",
                "operator": ">=",
                "value": "55",
                "unit": "years",
            },
            {
                "kind": "DEMOGRAPHIC",
                "field": "sex",
                "operator": "=",
                "value": "female",
            },
            {
                "kind": "OR",
                "children": [
                    {
                        "kind": "AND",
                        "children": [
                            _concept(
                                "271939006",
                                "Vaginal discharge (finding)",
                                "are presenting with these symptoms for the first time",
                                soft_qualifiers=[
                                    {
                                        "kind": "first_presentation",
                                        "enforcement": "soft",
                                    }
                                ],
                            ),
                            {
                                "kind": "AT_LEAST",
                                "min": 1,
                                "children": [
                                    _concept(
                                        "6631009",
                                        "Thrombocytosis (disorder)",
                                        "have thrombocytosis",
                                    ),
                                    _concept(
                                        "34436003",
                                        "Blood in urine (finding)",
                                        "report haematuria",
                                    ),
                                ],
                            },
                            _concept(
                                "271939006",
                                "Vaginal discharge (finding)",
                                "unexplained symptoms of vaginal discharge",
                            ),
                        ],
                    },
                    {
                        "kind": "AND",
                        "children": [
                            _concept(
                                "34436003",
                                "Blood in urine (finding)",
                                "visible haematuria, and:",
                            ),
                            _concept(
                                "165397008",
                                "Hemoglobin below reference range (finding)",
                                "low haemoglobin levels",
                            ),
                        ],
                    },
                ],
            },
        ],
    }


def _discharge_arm(tree: dict) -> dict:
    return tree["children"][2]["children"][0]


def test_discharge_arm_is_or_of_first_time_or_platelets_or_haematuria() -> None:
    out = reshape_1513_discharge_or(_and_discharge_with_platelets())
    arm = _discharge_arm(out)
    assert arm["kind"] == "AND"
    kinds = [c["kind"] for c in arm["children"]]
    assert kinds == ["CONCEPT", "OR"]
    unexplained = arm["children"][0]
    assert "unexplained" in unexplained["source_row_text"]
    quals = unexplained["criterion"]["soft_qualifiers"]
    assert any(q["kind"] == "unexplained" for q in quals)
    or_kids = arm["children"][1]["children"]
    sources = [c["source_row_text"] for c in or_kids]
    assert sources == [
        "are presenting with these symptoms for the first time",
        "have thrombocytosis",
        "report haematuria",
    ]
    first = or_kids[0]["criterion"]["soft_qualifiers"][0]
    assert first["kind"] == "first_presentation"
    assert first["enforcement"] == "soft"
    assert first["concept_id"] == "271939006"
    assert first["within_days"] == 90


def test_haematuria_arm_is_unchanged() -> None:
    original = _and_discharge_with_platelets()
    haem = deepcopy(original["children"][2]["children"][1])
    out = reshape_1513_discharge_or(original)
    assert out["children"][2]["children"][1] == haem


def test_does_not_mutate_input() -> None:
    original = _and_discharge_with_platelets()
    snapshot = deepcopy(original)
    reshape_1513_discharge_or(original)
    assert original == snapshot


def test_reshaped_tree_validates() -> None:
    out = reshape_1513_discharge_or(_and_discharge_with_platelets())
    ids = validate_logic_tree(LogicNode.model_validate(out))
    assert "271939006" in ids
    assert "6631009" in ids
    assert "34436003" in ids
