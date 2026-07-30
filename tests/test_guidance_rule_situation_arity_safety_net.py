"""Regression coverage for the NG12 1.3.1 situation-arity drift bug.

Bug: NG12 1.3.1's own ``listStructureJson`` has 7 top-level bullet items
(abdominal mass; change in bowel habit; iron-deficiency anaemia; age 40+
weight loss/abdominal pain; age <50 rectal bleeding + symptoms; age 50+
symptoms; age 60+ anaemia). The LAST bullet's own item text glues on 2
trailing whole-recommendation sentences that are NOT part of the bulleted
alternative list -- a NICE markup quirk where the final ``<li>`` absorbs
any prose that follows the list within the same paragraph. One of those
trailing sentences ("People with a rectal mass, an unexplained anal mass
or unexplained anal ulceration do not need to be offered FIT before
referral is considered") names 3 further findings.

An extraction that returned the legacy ``logic_tree`` shape directly
(bypassing ``_realign_verdict_to_skeleton``, which only fires for the
newer ``situation_draft`` shape) expanded those 3 findings into 3
additional top-level OR alternatives, producing a 10-branch OR from a
7-item source structure -- and it happened silently: nothing forced this
rule back to a human reviewer, even though those 3 findings already have
their own dedicated, correctly-actioned rules elsewhere in NG12 (1.3.5,
1.3.6) with a DIFFERENT action ("consider referral", no FIT) from this
rule's single rule-level action ("offer FIT").

This file pins the deterministic safety net that catches this pattern:
``_flag_situation_arity_drift`` compares the extracted tree's top-level OR
arity against the recommendation's own list-structure/prose-split shell
count and forces ``needs_human_review=True`` when the tree has MORE
branches than the source structure supports. It does not attempt to
repair the tree -- per R-4E4F22EF, the fix belongs to a human reviewer,
not a silent auto-merge, because this data model allows exactly one
ActionGroup per rule so the extra branches cannot simply be re-attached
with a different (correct) action.
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs import guidance_rule_extraction_v2_impl as impl

_NG12_1_3_1_VERBATIM = (
    "Offer quantitative faecal immunochemical testing (FIT) using "
    "HM-JACKarc or OC-Sensor to guide referral for suspected colorectal "
    "cancer in adults: with an abdominal mass, or with a change in bowel "
    "habit, or with iron-deficiency anaemia, or aged 40 and over with "
    "unexplained weight loss and abdominal pain, or aged under 50 with "
    "rectal bleeding and either of the following unexplained symptoms: "
    "abdominal pain weight loss, or aged 50 and over with any of the "
    "following unexplained symptoms: rectal bleeding abdominal pain "
    "weight loss, or aged 60 and over with anaemia even in the absence "
    "of iron deficiency. FIT should be offered even if the person has "
    "previously had a negative FIT result through the NHS bowel cancer "
    "screening programme. People with a rectal mass, an unexplained anal "
    "mass or unexplained anal ulceration do not need to be offered FIT "
    "before referral is considered. [2023]"
)

_NG12_1_3_1_LIST_STRUCTURE = {
    "lead_text": (
        "Offer quantitative faecal immunochemical testing (FIT) using "
        "HM-JACKarc or OC-Sensor to guide referral for suspected "
        "colorectal cancer in adults:"
    ),
    "items": [
        {"text": "with an abdominal mass"},
        {"text": "with a change in bowel habit"},
        {"text": "with iron-deficiency anaemia"},
        {"text": "aged 40 and over with unexplained weight loss and abdominal pain"},
        {
            "text": (
                "aged under 50 with rectal bleeding and either of the "
                "following unexplained symptoms:"
            ),
            "children": [
                {"text": "abdominal pain"},
                {"text": "weight loss"},
            ],
        },
        {
            "text": (
                "aged 50 and over with any of the following unexplained "
                "symptoms:"
            ),
            "children": [
                {"text": "rectal bleeding"},
                {"text": "abdominal pain"},
                {"text": "weight loss"},
            ],
        },
        {
            "text": (
                "aged 60 and over with anaemia even in the absence of "
                "iron deficiency. FIT should be offered even if the "
                "person has previously had a negative FIT result "
                "through the NHS bowel cancer screening programme. "
                "People with a rectal mass, an unexplained anal mass or "
                "unexplained anal ulceration do not need to be offered "
                "FIT before referral is considered. [2023]"
            )
        },
    ],
}


def _bare_concept(text: str) -> dict:
    return {"kind": "concept", "term": {"text": text}}


def _demographic_and(age_op: str, age_value: float, *symptoms: str) -> dict:
    return {
        "kind": "AND",
        "children": [
            {"kind": "demographic", "field": "age", "operator": age_op, "value": age_value},
            *[_bare_concept(s) for s in symptoms],
        ],
    }


def _ng12_1_3_1_buggy_ten_branch_tree() -> dict:
    """The exact 10-branch shape reported by the reviewer (A-J)."""
    return {
        "kind": "OR",
        "children": [
            _bare_concept("abdominal mass"),
            _bare_concept("change in bowel habit"),
            _bare_concept("iron-deficiency anaemia"),
            _demographic_and(">=", 40, "weight loss", "abdominal pain"),
            _demographic_and("<", 50, "rectal bleeding", "abdominal pain", "weight loss"),
            _demographic_and(">=", 50, "rectal bleeding", "abdominal pain", "weight loss"),
            _demographic_and(">=", 60, "anaemia"),
            _bare_concept("rectal mass"),
            _bare_concept("anal mass"),
            _bare_concept("anal ulceration"),
        ],
    }


def _ng12_1_3_1_correct_seven_branch_tree() -> dict:
    """The 7-branch shape matching the recommendation's own list structure."""
    tree = _ng12_1_3_1_buggy_ten_branch_tree()
    tree["children"] = tree["children"][:7]
    return tree


# ---------------------------------------------------------------------------
# _tree_top_level_or_children
# ---------------------------------------------------------------------------


def test_tree_top_level_or_children_reads_bare_or():
    tree = {"kind": "OR", "children": [_bare_concept("a"), _bare_concept("b")]}
    result = impl._tree_top_level_or_children(tree)
    assert result is not None
    assert len(result) == 2


def test_tree_top_level_or_children_reads_and_wrapped_or():
    tree = {
        "kind": "AND",
        "children": [
            {"kind": "demographic", "field": "age", "operator": ">=", "value": 18},
            {"kind": "OR", "children": [_bare_concept("a"), _bare_concept("b")]},
        ],
    }
    result = impl._tree_top_level_or_children(tree)
    assert result is not None
    assert len(result) == 2


def test_tree_top_level_or_children_none_for_single_leaf():
    assert impl._tree_top_level_or_children(_bare_concept("a")) is None


def test_tree_top_level_or_children_none_for_ambiguous_multi_or_and():
    tree = {
        "kind": "AND",
        "children": [
            {"kind": "OR", "children": [_bare_concept("a")]},
            {"kind": "OR", "children": [_bare_concept("b")]},
        ],
    }
    assert impl._tree_top_level_or_children(tree) is None


# ---------------------------------------------------------------------------
# _flag_situation_arity_drift
# ---------------------------------------------------------------------------


def test_flag_situation_arity_drift_escalates_on_ng12_1_3_1_defect_pattern():
    rec = {
        "verbatim": _NG12_1_3_1_VERBATIM,
        "list_structure": _NG12_1_3_1_LIST_STRUCTURE,
    }
    coded = {"logic_tree": _ng12_1_3_1_buggy_ten_branch_tree()}

    out = impl._flag_situation_arity_drift(rec, coded)

    assert out["needs_human_review"] is True
    reasons = [item.get("reason") for item in out["hitl_terms"]]
    assert "situation_count_exceeds_source_structure" in reasons
    detail = out["hitl_terms"][-1]["detail"]
    assert "7 situation" in detail
    assert "10 top-level OR branches" in detail


def test_flag_situation_arity_drift_noop_when_arity_matches_structure():
    rec = {
        "verbatim": _NG12_1_3_1_VERBATIM,
        "list_structure": _NG12_1_3_1_LIST_STRUCTURE,
    }
    coded = {"logic_tree": _ng12_1_3_1_correct_seven_branch_tree()}

    out = impl._flag_situation_arity_drift(rec, coded)

    assert "needs_human_review" not in out


def test_flag_situation_arity_drift_noop_when_arity_is_fewer_than_structure():
    # Under-count is not this safety net's concern -- the sex/age checks
    # cover dropped constraints; this net only targets invented branches.
    rec = {
        "verbatim": _NG12_1_3_1_VERBATIM,
        "list_structure": _NG12_1_3_1_LIST_STRUCTURE,
    }
    tree = _ng12_1_3_1_correct_seven_branch_tree()
    tree["children"] = tree["children"][:5]
    coded = {"logic_tree": tree}

    out = impl._flag_situation_arity_drift(rec, coded)

    assert "needs_human_review" not in out


def test_flag_situation_arity_drift_noop_on_single_situation_recommendation():
    rec = {"verbatim": "adults with a fasting glucose above 7 mmol/L"}
    coded = {"logic_tree": _bare_concept("glucose")}

    out = impl._flag_situation_arity_drift(rec, coded)

    assert "needs_human_review" not in out


def test_flag_situation_arity_drift_accepts_json_encoded_list_structure():
    import json

    rec = {
        "verbatim": _NG12_1_3_1_VERBATIM,
        "list_structure_json": json.dumps(_NG12_1_3_1_LIST_STRUCTURE),
    }
    coded = {"logic_tree": _ng12_1_3_1_buggy_ten_branch_tree()}

    out = impl._flag_situation_arity_drift(rec, coded)

    assert out["needs_human_review"] is True


def test_flag_situation_arity_drift_does_not_raise_on_malformed_tree():
    rec = {
        "verbatim": _NG12_1_3_1_VERBATIM,
        "list_structure": _NG12_1_3_1_LIST_STRUCTURE,
    }
    coded = {"logic_tree": "not-a-tree"}

    out = impl._flag_situation_arity_drift(rec, coded)

    assert "needs_human_review" not in out
