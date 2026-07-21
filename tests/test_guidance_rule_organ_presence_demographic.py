"""Regression coverage for the dropped-age/anatomy trans-inclusive fix.

Bug: NICE recommendations that widen a gendered population to trans and
non-binary patients (e.g. "women, and trans men and non-binary people with
female reproductive organs who are aged 39 or under...") were extracted
with BOTH the age threshold and the population scope dropped entirely --
worse than the plain sex-drop case fixed for R-4E4F22EF, since the rule
ends up with no demographic scoping at all (confirmed empirically on
NG12 recommendation 1.5.6).

Forcing this clause into the binary `sex` demographic field would also be
wrong: a trans man in this population may be recorded as `sex=male` in
the patient record, so `sex="female"` would wrongly EXCLUDE the exact
patients the guideline means to include. The fix routes anatomy scope to
a `concept` leaf instead, using the same reproductive-anatomy vocabulary
already established for DI-9AA2CDA5's runtime anatomy-conflict check
(guideline_evaluator._FEMALE_ANATOMY_SNOMED / _MALE_ANATOMY_SNOMED).

This file pins three independent layers of the fix, mirroring
test_guidance_rule_sex_demographic.py:
1. The legacy flat-term fallback (`_make_demographic_or_concept`) emits an
   anatomy `concept` leaf ANDed with age, instead of a `sex` demographic
   or dropping the clause entirely.
2. `assemble_result`'s deterministic safety net
   (`_flag_missing_age_or_organ_constraint`) forces human review when the
   source text uses trans-inclusive/organ wording but the tree is missing
   the age leaf and/or any anatomy/sex leaf.
3. The safety net does not fire on ordinary sex-only recommendations, so
   it does not double up with `_flag_missing_sex_constraint` noise.
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs import guidance_rule_extraction_v2_impl as impl

_NG12_1_5_6_VERBATIM = (
    "1.5.6 For women, and trans men and non-binary people with female "
    "reproductive organs who are aged 39 or under with persistent "
    "symptoms that suggest ovarian cancer"
)

_NG23_1_3_1_VERBATIM = (
    "1.3.1 Offer a diagnostic test for premature ovarian insufficiency to "
    "women, and trans men and non-binary people registered female at "
    "birth who are aged 45 or over and have menopausal symptoms"
)


# ---------------------------------------------------------------------------
# Layer 1: legacy flat-term fallback
# ---------------------------------------------------------------------------


def test_parse_organ_presence_constraint_detects_female_reproductive_organs():
    term = "trans men and non-binary people with female reproductive organs"
    result = impl._parse_organ_presence_constraint(term)
    assert result["kind"] == "concept"
    assert result["term"]["text"] == "presence of female reproductive organs"
    assert "uterus" in result["term"]["search_terms"]


def test_parse_organ_presence_constraint_detects_registered_at_birth():
    term = "trans men and non-binary people registered female at birth"
    result = impl._parse_organ_presence_constraint(term)
    assert result["term"]["text"] == "presence of female reproductive organs"


def test_parse_organ_presence_constraint_detects_male_variant():
    term = "trans women and non-binary people with male reproductive organs"
    result = impl._parse_organ_presence_constraint(term)
    assert result["term"]["text"] == "presence of male reproductive organs"
    assert "prostate gland" in result["term"]["search_terms"]


def test_parse_organ_presence_constraint_requires_both_cue_and_organ():
    # "trans" cue alone, no organ/birth-registration qualifier -> no match.
    assert impl._parse_organ_presence_constraint("trans men in the cohort") is None
    # organ qualifier alone, no trans-inclusive cue -> no match (this is
    # exactly the plain sex+age case, handled by _parse_sex_constraint).
    assert (
        impl._parse_organ_presence_constraint("women with female reproductive organs")
        is None
    )


def test_make_demographic_or_concept_ands_age_and_organ_leaf():
    leaf = impl._make_demographic_or_concept(
        "trans men and non-binary people with female reproductive organs "
        "aged 39 or under"
    )
    assert leaf["kind"] == "AND"
    kinds = {child["kind"] for child in leaf["children"]}
    assert kinds == {"demographic", "concept"}
    age_child = next(c for c in leaf["children"] if c["kind"] == "demographic")
    assert age_child["field"] == "age"
    assert age_child["value"] == 39.0
    concept_child = next(c for c in leaf["children"] if c["kind"] == "concept")
    assert concept_child["term"]["text"] == "presence of female reproductive organs"


def test_make_demographic_or_concept_prefers_organ_over_plain_sex_match():
    # "women, ... with female reproductive organs" would otherwise also
    # match _parse_sex_constraint on "women" -- organ wording must win so
    # the trans-inclusive population is not wrongly excluded.
    leaf = impl._make_demographic_or_concept(
        "women, and trans men and non-binary people with female " "reproductive organs"
    )
    assert leaf["kind"] == "concept"
    assert leaf["term"]["text"] == "presence of female reproductive organs"


# ---------------------------------------------------------------------------
# Layer 2: assemble_result safety net
# ---------------------------------------------------------------------------


def test_flag_missing_age_or_organ_constraint_escalates_when_both_dropped():
    rec = {"verbatim": _NG12_1_5_6_VERBATIM}
    coded = {"logic_tree": {"kind": "concept", "term": {"text": "ovarian symptoms"}}}

    out = impl._flag_missing_age_or_organ_constraint(rec, coded)

    assert out["needs_human_review"] is True
    reasons = [item.get("reason") for item in out["hitl_terms"]]
    assert "trans_inclusive_population_scope_possibly_dropped" in reasons
    detail = out["hitl_terms"][-1]["detail"]
    assert "age_constraint_possibly_dropped" in detail
    assert "anatomy_scope_possibly_dropped" in detail


def test_flag_missing_age_or_organ_constraint_noop_when_both_present():
    rec = {"verbatim": _NG12_1_5_6_VERBATIM}
    coded = {
        "logic_tree": {
            "kind": "AND",
            "children": [
                {"kind": "demographic", "field": "age", "value": 39},
                {
                    "kind": "concept",
                    "term": {"text": "presence of female reproductive organs"},
                },
            ],
        }
    }

    out = impl._flag_missing_age_or_organ_constraint(rec, coded)

    assert "needs_human_review" not in out


def test_flag_missing_age_or_organ_constraint_accepts_sex_leaf_as_anatomy_signal():
    # A plain sex demographic leaf still counts as an anatomy/sex signal --
    # this safety net only escalates when NEITHER a sex leaf NOR an organ
    # concept leaf is present.
    rec = {"verbatim": _NG23_1_3_1_VERBATIM}
    coded = {
        "logic_tree": {
            "kind": "AND",
            "children": [
                {"kind": "demographic", "field": "age", "value": 45},
                {"kind": "demographic", "field": "sex", "value": "female"},
            ],
        }
    }

    out = impl._flag_missing_age_or_organ_constraint(rec, coded)

    assert "needs_human_review" not in out


def test_flag_missing_age_or_organ_constraint_noop_on_ordinary_recommendation():
    rec = {"verbatim": "adults with a fasting glucose above 7 mmol/L"}
    coded = {"logic_tree": {"kind": "concept", "term": {"text": "glucose"}}}

    out = impl._flag_missing_age_or_organ_constraint(rec, coded)

    assert "needs_human_review" not in out


def test_tree_has_organ_or_sex_node_detects_organ_concept_leaf():
    tree = {
        "kind": "AND",
        "children": [
            {
                "kind": "concept",
                "term": {"text": "presence of male reproductive organs"},
            }
        ],
    }
    assert impl._tree_has_organ_or_sex_node(tree) is True


def test_tree_has_age_node_false_when_only_concept_leaves_present():
    tree = {"kind": "concept", "term": {"text": "ovarian symptoms"}}
    assert impl._tree_has_age_node(tree) is False
