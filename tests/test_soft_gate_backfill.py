"""Propose-then-confirm tags for soft gates and FIT policy.

Atlas: DI-C136E4B7, DI-55CCC312
"""

from __future__ import annotations

from libs.guidelines.soft_gate_backfill import (
    ALLOW_APPLY,
    propose_soft_gate,
)


def test_proposes_first_presentation_for_1513_verbatim() -> None:
    proposal = propose_soft_gate(
        "1.5.13",
        "Consider a transvaginal ultrasound scan to assess for endometrial "
        "cancer in women aged 55 and over with unexplained vaginal discharge "
        "who are presenting for the first time.",
    )
    assert proposal["soft_kinds"] == ["first_presentation"]
    assert proposal["investigation_policy"] is None


def test_proposes_fit_required_for_131() -> None:
    proposal = propose_soft_gate(
        "1.3.1",
        "Offer quantitative faecal immunochemical testing (FIT) to assess "
        "for colorectal cancer in adults.",
    )
    assert proposal["investigation_policy"] == "required"


def test_proposes_not_required_for_mass_bypass() -> None:
    for rec in ("1.3.5", "1.3.6"):
        proposal = propose_soft_gate(rec, "Refer people with a rectal or anal mass.")
        assert proposal["investigation_policy"] == "not_required"


def test_allow_list_is_the_auto_apply_set() -> None:
    assert ALLOW_APPLY == frozenset({"1.5.13", "1.3.1", "1.3.5", "1.3.6"})


def test_tags_first_presentation_leaf_from_source_row() -> None:
    from libs.guidelines.soft_gate_backfill import tag_first_presentation_leaves

    tree = {
        "kind": "AND",
        "children": [
            {
                "kind": "CONCEPT",
                "source_row_text": "are presenting with these symptoms for the first time",
                "criterion": {"snomed_concept_id": "1", "preferred_term": "Discharge"},
            }
        ],
    }
    out = tag_first_presentation_leaves(tree)
    quals = out["children"][0]["criterion"]["soft_qualifiers"]
    assert quals == [{"kind": "first_presentation", "enforcement": "soft"}]


def test_unexplained_only_is_not_auto_applied() -> None:
    proposal = propose_soft_gate(
        "1.1.2",
        "Refer people with unexplained chest pain.",
    )
    assert "1.1.2" not in ALLOW_APPLY
    assert proposal["soft_kinds"] == ["unexplained"]


def test_tags_unexplained_and_persistent_as_hard_from_source_text() -> None:
    from libs.guidelines.soft_gate_backfill import tag_first_presentation_leaves

    tree = {
        "kind": "AND",
        "children": [
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": "125605004",
                    "preferred_term": "Fracture of bone",
                    "source_text": "unexplained fracture",
                },
            },
            {
                "kind": "CONCEPT",
                "source_row_text": "persistent bone pain",
                "criterion": {
                    "snomed_concept_id": "12584003",
                    "preferred_term": "Bone pain",
                },
            },
        ],
    }
    out = tag_first_presentation_leaves(tree)
    unexplained = out["children"][0]["criterion"]["soft_qualifiers"]
    persistent = out["children"][1]["criterion"]["soft_qualifiers"]
    assert unexplained == [{"kind": "unexplained", "enforcement": "hard"}]
    assert persistent == [{"kind": "persistent", "enforcement": "hard"}]
