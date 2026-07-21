"""Regression coverage for the dropped-sex-constraint safety fix.

Bug: NICE recommendations routinely give a different age threshold for
women and men in the same clause (e.g. "women aged 65 years and over and
men aged 75 years and over"). Extraction could silently drop the sex leaf
while still getting the age leaf right, producing a rule that looks
complete to a reviewer but matches the wrong patient population
(Risk R-4E4F22EF).

This file pins three independent layers of the fix:
1. The legacy flat-term fallback (`_make_demographic_or_concept`) ANDs age
   and sex together instead of returning only the first match.
2. `assemble_result`'s deterministic safety net
   (`_flag_missing_sex_constraint`) forces human review when the source
   text is sex-specific but the tree has no `sex` demographic node.
3. `GuidanceRuleGenerator._build_verifier_payload` actually persists that
   review flag into the stored `verifierJson`, so the UI "Needs review"
   chip lights up instead of the flag being silently dropped on write.
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs import guidance_rule_extraction_v2_impl as impl
from services.api.app.services.guidance_rule_generator import GuidanceRuleGenerator


# ---------------------------------------------------------------------------
# Layer 1: legacy flat-term fallback
# ---------------------------------------------------------------------------


def test_parse_sex_constraint_detects_sex_embedded_in_longer_phrase():
    assert impl._parse_sex_constraint("women aged 65 years and over") == {
        "field": "sex",
        "operator": "=",
        "value": "female",
        "raw_term": "women aged 65 years and over",
    }
    assert impl._parse_sex_constraint("all men aged 75 years and over") == {
        "field": "sex",
        "operator": "=",
        "value": "male",
        "raw_term": "all men aged 75 years and over",
    }


def test_parse_sex_constraint_does_not_false_positive_on_women_as_men():
    # "women" contains the letters "men" as a substring; the word-boundary
    # regex must not mistake it for a match on the male term.
    result = impl._parse_sex_constraint("women only clinic")
    assert result["value"] == "female"


def test_parse_sex_constraint_returns_none_without_a_sex_word():
    assert impl._parse_sex_constraint("previous fragility fracture") is None


def test_make_demographic_or_concept_ands_age_and_sex_together():
    leaf = impl._make_demographic_or_concept("all women aged 65 years and over")
    assert leaf["kind"] == "AND"
    fields = {child["field"] for child in leaf["children"]}
    assert fields == {"age", "sex"}
    sex_child = next(c for c in leaf["children"] if c["field"] == "sex")
    assert sex_child["value"] == "female"
    age_child = next(c for c in leaf["children"] if c["field"] == "age")
    assert age_child["value"] == 65.0
    assert age_child["operator"] == ">="


def test_make_demographic_or_concept_still_handles_age_only():
    leaf = impl._make_demographic_or_concept("age 40 and over")
    assert leaf == {
        "kind": "demographic",
        "field": "age",
        "operator": ">=",
        "value": 40.0,
        "unit": "years",
        "raw_term": "age 40 and over",
    }


def test_make_demographic_or_concept_still_handles_sex_only():
    leaf = impl._make_demographic_or_concept("female sex")
    assert leaf == {
        "kind": "demographic",
        "field": "sex",
        "operator": "=",
        "value": "female",
        "raw_term": "female sex",
    }


def test_make_demographic_or_concept_falls_back_to_concept():
    leaf = impl._make_demographic_or_concept("previous fragility fracture")
    assert leaf["kind"] == "concept"
    assert leaf["term"]["text"] == "previous fragility fracture"


# ---------------------------------------------------------------------------
# Layer 2: assemble_result safety net
# ---------------------------------------------------------------------------


def _age_only_or_tree() -> dict:
    """Mimics the reported bug: 2 age-only branches, no sex leaf anywhere."""
    return {
        "kind": "OR",
        "children": [
            {
                "kind": "demographic",
                "field": "age",
                "operator": ">=",
                "value": 65,
                "unit": "years",
            },
            {
                "kind": "demographic",
                "field": "age",
                "operator": ">=",
                "value": 75,
                "unit": "years",
            },
        ],
    }


def test_tree_has_sex_node_false_when_only_age_leaves_present():
    assert impl._tree_has_sex_node(_age_only_or_tree()) is False


def test_tree_has_sex_node_true_when_nested_under_and():
    tree = {
        "kind": "OR",
        "children": [
            {
                "kind": "AND",
                "children": [
                    {"kind": "demographic", "field": "age", "value": 65},
                    {"kind": "demographic", "field": "sex", "value": "female"},
                ],
            }
        ],
    }
    assert impl._tree_has_sex_node(tree) is True


def test_flag_missing_sex_constraint_escalates_when_sex_wording_present():
    rec = {"verbatim": "in all women aged 65 years and over and men aged 75"}
    coded = {"logic_tree": _age_only_or_tree()}

    out = impl._flag_missing_sex_constraint(rec, coded)

    assert out["needs_human_review"] is True
    reasons = [item.get("reason") for item in out["hitl_terms"]]
    assert "sex_constraint_possibly_dropped" in reasons


def test_flag_missing_sex_constraint_noop_when_sex_leaf_present():
    rec = {"verbatim": "in all women aged 65 years and over"}
    coded = {
        "logic_tree": {
            "kind": "AND",
            "children": [
                {"kind": "demographic", "field": "age", "value": 65},
                {"kind": "demographic", "field": "sex", "value": "female"},
            ],
        }
    }

    out = impl._flag_missing_sex_constraint(rec, coded)

    assert "needs_human_review" not in out
    assert "hitl_terms" not in out


def test_flag_missing_sex_constraint_noop_when_verbatim_is_sex_neutral():
    rec = {"verbatim": "adults with a fasting glucose above 7 mmol/L"}
    coded = {"logic_tree": _age_only_or_tree()}

    out = impl._flag_missing_sex_constraint(rec, coded)

    assert "needs_human_review" not in out


# ---------------------------------------------------------------------------
# Layer 3: verifier_json persistence actually carries the flag
# ---------------------------------------------------------------------------


def test_build_verifier_payload_merges_needs_human_review_into_llm_verdict():
    coded = {
        "verifier": {"overall_status": "verified", "leaf_decisions": []},
        "needs_human_review": True,
        "hitl_terms": [{"kind": "safety_check", "reason": "x"}],
    }

    payload = GuidanceRuleGenerator._build_verifier_payload(coded)

    assert payload["overall_status"] == "verified"
    assert payload["needs_human_review"] is True
    assert payload["hitl_terms"] == coded["hitl_terms"]


def test_build_verifier_payload_includes_pipeline_errors():
    coded = {"verifier": {"overall_status": "verified"}}
    errors = ["terminology_api_unavailable:boom"]

    payload = GuidanceRuleGenerator._build_verifier_payload(coded, errors)

    assert payload["errors"] == errors


def test_build_verifier_payload_returns_none_when_nothing_to_report():
    assert GuidanceRuleGenerator._build_verifier_payload({}) is None


def test_build_verifier_payload_preserves_true_llm_verdict_when_review_not_needed():
    coded = {"verifier": {"overall_status": "verified"}}

    payload = GuidanceRuleGenerator._build_verifier_payload(coded)

    assert payload == {"overall_status": "verified"}
    assert "needs_human_review" not in payload
