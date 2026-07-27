"""Unit tests for SituationDraft compile (schema_version 2 logic trees).

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
"""

from __future__ import annotations

from libs.guidance.situation_draft import (
    SituationDraft,
    SituationShell,
    align_draft_to_skeleton,
    compile_situation_draft,
    empty_situation_shells,
    tree_shells_from_threshold_rows,
)


def _concept(text: str) -> dict:
    return {"kind": "concept", "term": {"text": text, "search_terms": [text]}}


def _age(years: int) -> dict:
    return {
        "kind": "demographic",
        "field": "age",
        "operator": ">=",
        "value": years,
        "unit": "years",
    }


def test_compile_single_situation_flattens_into_and():
    draft = SituationDraft(
        prerequisites=[_age(55)],
        situations=[
            SituationShell(
                text="treatment-resistant dyspepsia",
                source="single",
                conditions=[_concept("dyspepsia")],
            )
        ],
    )
    tree = compile_situation_draft(draft)
    assert tree["kind"] == "AND"
    assert tree["children"][0]["kind"] == "demographic"
    assert tree["children"][1]["kind"] == "concept"


def test_compile_two_plus_situations_builds_or_of_pathway_ands():
    draft = SituationDraft(
        prerequisites=[_age(55)],
        situations=[
            SituationShell(
                text="dyspepsia",
                source="structure",
                conditions=[_concept("dyspepsia")],
            ),
            SituationShell(
                text="haematemesis",
                source="structure",
                conditions=[_concept("haematemesis")],
            ),
            SituationShell(
                text="weight loss",
                source="structure",
                conditions=[_concept("weight loss")],
            ),
            SituationShell(
                text="raised platelets",
                source="structure",
                conditions=[_concept("thrombocytosis")],
            ),
        ],
    )
    tree = compile_situation_draft(draft)
    assert tree["kind"] == "AND"
    assert tree["children"][0]["kind"] == "demographic"
    or_node = tree["children"][1]
    assert or_node["kind"] == "OR"
    assert len(or_node["children"]) == 4
    for child in or_node["children"]:
        assert child["kind"] == "AND"
        assert str(child.get("pathway_key") or "").startswith("pw_")
        assert len(child["children"]) == 1


def test_compile_without_prerequisites_returns_bare_or():
    draft = SituationDraft(
        situations=[
            SituationShell(text="A", source="heuristic", conditions=[_concept("a")]),
            SituationShell(text="B", source="heuristic", conditions=[_concept("b")]),
        ]
    )
    tree = compile_situation_draft(draft)
    assert tree["kind"] == "OR"
    assert len(tree["children"]) == 2


def test_empty_situation_shells_preserve_count_for_stubs():
    shells = [
        SituationShell(text="A", source="structure"),
        SituationShell(text="B", source="structure"),
        SituationShell(text="C", source="structure"),
        SituationShell(text="D", source="structure"),
    ]
    tree = empty_situation_shells(shells)
    assert tree["kind"] == "OR"
    assert len(tree["children"]) == 4
    assert all(c["children"] == [] for c in tree["children"])


def test_align_draft_to_skeleton_pads_and_trims():
    draft = SituationDraft(
        situations=[
            SituationShell(
                text="wrong", source="heuristic", conditions=[_concept("a")]
            ),
            SituationShell(
                text="extra", source="heuristic", conditions=[_concept("b")]
            ),
            SituationShell(text="drop", source="heuristic", conditions=[_concept("c")]),
        ]
    )
    skeleton = [
        SituationShell(text="A", start=0, end=1, source="structure"),
        SituationShell(text="B", start=2, end=3, source="structure"),
    ]
    aligned = align_draft_to_skeleton(draft, skeleton)
    assert len(aligned.situations) == 2
    assert aligned.situations[0].text == "A"
    assert aligned.situations[0].conditions[0]["term"]["text"] == "a"
    assert aligned.situations[1].text == "B"


def test_tree_shells_from_threshold_rows():
    shells = tree_shells_from_threshold_rows(
        ["PSA 3-10", "PSA >10", {"text": "PSA rising"}]
    )
    assert len(shells) == 3
    assert all(s.source == "tree" for s in shells)
    assert shells[0].text == "PSA 3-10"
