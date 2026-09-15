"""Tests for GuidelineEvaluator -- VT-LEO-AI-065."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator


def _make_store(current_ruleset=None, int_id_map=None, bitmaps=None):
    """Build a mock BitmapStore with configurable state."""
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = current_ruleset
    store.get_ruleset.return_value = current_ruleset
    int_id_map = int_id_map or {}
    bitmaps = bitmaps or {}
    # Single-key accessors (legacy paths)
    store.get_int_id.side_effect = lambda cid: int_id_map.get(cid)
    store.get_bitmap.side_effect = lambda bid: bitmaps.get(bid)
    # Bulk accessors used by evaluate_patient and diagnose
    store.get_int_ids_bulk.side_effect = lambda cids: {
        c: int_id_map[c] for c in cids if c in int_id_map
    }
    store.get_bitmaps_bulk.side_effect = lambda bids: {
        b: bitmaps[b] for b in bids if b in bitmaps
    }
    return store


def _put_bitmap(int_ids):
    """Helper to build a BitMap from a list and return serialised + store dict."""
    bm = BitMap(int_ids)
    return bm


@pytest.fixture()
def evaluator_factory():
    def make(current_ruleset=None, int_id_map=None, bitmaps=None):
        store = _make_store(current_ruleset, int_id_map, bitmaps)
        return GuidelineEvaluator(store=store)

    return make


class TestNoActiveRuleset:
    def test_returns_empty_matches_and_message_when_no_ruleset(self, evaluator_factory):
        """Returns informative response when no ruleset has been compiled."""
        ev = evaluator_factory(current_ruleset=None)
        result = ev.evaluate_patient(["443416000"])
        assert result["matched_rules"] == []
        assert result["active_version"] is None
        assert "No active ruleset" in result.get("message", "")


def test_evaluator_uses_scoped_ruleset_when_version_requested(evaluator_factory):
    bm = BitMap([1])
    ruleset = {
        "version": "vScope",
        "rules": [_make_rule(criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}])],
    }
    ev = evaluator_factory(
        current_ruleset=ruleset,
        int_id_map={"443416000": 1},
        bitmaps={"bm1": bm},
    )
    result = ev.evaluate_patient(
        ["443416000"],
        scope_type="guideline",
        scope_id="NG12",
        ruleset_version="vScope",
    )
    assert len(result["matched_rules"]) == 1
    ev._store.get_ruleset.assert_called_once_with(
        "vScope",
        scope_type="guideline",
        scope_id="NG12",
    )


def _make_rule(
    rule_id="r1", guideline_id="NG151", criteria_groups=None, applies_to=None
):
    """Build a compiled rule dict in the new criteria_groups format."""
    return {
        "rule_id": rule_id,
        "name": "Test rule",
        "strength": "refer",
        "guideline_id": guideline_id,
        "guideline_title": "Bowel cancer",
        "chapter_title": None,
        "recommendation_verbatim": "Refer for rectal bleeding",
        "schema_version": 1,
        "criteria_groups": criteria_groups or [],
        "applies_to": applies_to or [],
        "action": None,
    }


class TestRequiredCriteriaMatching:
    """Rule matches when ALL-mode group criteria are in the patient's code set."""

    def test_rule_matches_when_all_group_concept_present(self, evaluator_factory):
        """A rule with mode=ALL matches when patient has all required concepts."""
        bm = BitMap([1])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}])
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["443416000"])
        assert len(result["matched_rules"]) == 1
        assert result["matched_rules"][0]["rule_id"] == "r1"

    def test_rule_does_not_match_when_all_group_concept_missing(
        self, evaluator_factory
    ):
        """A rule does not match when patient is missing a required concept."""
        bm = BitMap([1])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}])
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"999999": 2},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["999999"])
        assert result["matched_rules"] == []


class TestAnyModeMatching:
    """Rule matches when ANY-mode group has at least one concept in patient set."""

    def test_rule_matches_when_any_concept_present(self, evaluator_factory):
        """mode=ANY fires when patient has at least one of the symptom concepts."""
        bm = BitMap([1, 2, 3])  # three possible symptoms
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(criteria_groups=[{"mode": "ANY", "bitmap_id": "bm1"}])
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"cough": 1},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["cough"])  # patient has only one of the symptoms
        assert len(result["matched_rules"]) == 1

    def test_rule_does_not_match_when_no_any_concept_present(self, evaluator_factory):
        """mode=ANY does not fire when patient has none of the symptom concepts."""
        bm = BitMap([1, 2, 3])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(criteria_groups=[{"mode": "ANY", "bitmap_id": "bm1"}])
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"other_code": 99},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["other_code"])
        assert result["matched_rules"] == []


class TestNotModeExclusion:
    """Rule does not match when NOT-mode group concept is in patient set."""

    def test_rule_excluded_when_not_concept_present(self, evaluator_factory):
        """mode=NOT (formerly forbid) excludes rule when patient has the concept."""
        req_bm = BitMap([1])
        not_bm = BitMap([2])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(
                    criteria_groups=[
                        {"mode": "ALL", "bitmap_id": "bm_all"},
                        {"mode": "NOT", "bitmap_id": "bm_not"},
                    ]
                )
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"req_code": 1, "excl_code": 2},
            bitmaps={"bm_all": req_bm, "bm_not": not_bm},
        )
        result = ev.evaluate_patient(["req_code", "excl_code"])
        assert (
            result["matched_rules"] == []
        ), "Rule should be excluded when patient has a NOT-mode concept"

    def test_rule_matches_when_patient_lacks_not_concept(self, evaluator_factory):
        """Rule matches when patient has required codes but not the excluded concept."""
        req_bm = BitMap([1])
        not_bm = BitMap([2])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(
                    criteria_groups=[
                        {"mode": "ALL", "bitmap_id": "bm_all"},
                        {"mode": "NOT", "bitmap_id": "bm_not"},
                    ]
                )
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"req_code": 1},
            bitmaps={"bm_all": req_bm, "bm_not": not_bm},
        )
        result = ev.evaluate_patient(["req_code"])
        assert len(result["matched_rules"]) == 1


class TestUnknownCodes:
    """Unknown patient codes are silently skipped."""

    def test_unknown_patient_codes_are_skipped(self, evaluator_factory):
        """Concept IDs not in the int_id store are excluded from the patient bitmap."""
        bm = BitMap([1])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}])
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["UNKNOWN_CODE"])
        assert result["matched_rules"] == []


class TestPathwayFilter:
    """pathway_filter restricts evaluation to a specific guideline."""

    def test_pathway_filter_excludes_other_guidelines(self, evaluator_factory):
        """Rules for other guidelines are excluded when pathway_filter is set."""
        bm = BitMap([1])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(
                    rule_id="r1",
                    guideline_id="CG89",
                    criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}],
                )
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["443416000"], pathway_filter="NG151")
        assert result["matched_rules"] == []


class TestSchemaV2LogicTree:
    def test_schema_v2_and_or_age_logic_matches(self, evaluator_factory):
        bm_bleed = BitMap([1])
        bm_pain = BitMap([2])
        ruleset = {
            "version": "v2",
            "rules": [
                {
                    "rule_id": "r2",
                    "name": "Exact rule",
                    "strength": "refer",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "guideline_title": "Cancer",
                    "chapter_title": None,
                    "recommendation_verbatim": "test",
                    "logic_tree": {
                        "kind": "AND",
                        "children": [
                            {
                                "kind": "DEMOGRAPHIC",
                                "field": "age",
                                "operator": ">=",
                                "value": 40,
                                "unit": "years",
                            },
                            {
                                "kind": "OR",
                                "children": [
                                    {"kind": "concept", "bitmap_id": "bm_bleed"},
                                    {"kind": "concept", "bitmap_id": "bm_pain"},
                                ],
                            },
                        ],
                    },
                    "action": None,
                }
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"bleed": 1},
            bitmaps={"bm_bleed": bm_bleed, "bm_pain": bm_pain},
        )
        result = ev.evaluate_patient(["bleed"], patient_age=45)
        assert len(result["matched_rules"]) == 1

    def test_schema_v2_fails_closed_without_age(self, evaluator_factory):
        bm_bleed = BitMap([1])
        ruleset = {
            "version": "v2",
            "rules": [
                {
                    "rule_id": "r2",
                    "name": "Exact rule",
                    "strength": "refer",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "guideline_title": "Cancer",
                    "chapter_title": None,
                    "recommendation_verbatim": "test",
                    "logic_tree": {
                        "kind": "AND",
                        "children": [
                            {
                                "kind": "DEMOGRAPHIC",
                                "field": "age",
                                "operator": ">=",
                                "value": 40,
                                "unit": "years",
                            },
                            {"kind": "concept", "bitmap_id": "bm_bleed"},
                        ],
                    },
                    "action": None,
                }
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"bleed": 1},
            bitmaps={"bm_bleed": bm_bleed},
        )
        result = ev.evaluate_patient(["bleed"])
        assert result["matched_rules"] == []

    def test_schema_v2_at_least_matches_threshold(self, evaluator_factory):
        bm_cough = BitMap([1])
        bm_weight = BitMap([2])
        bm_fatigue = BitMap([3])
        ruleset = {
            "version": "v2",
            "rules": [
                {
                    "rule_id": "r3",
                    "name": "AT_LEAST test",
                    "strength": "refer",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "guideline_title": "Cancer",
                    "chapter_title": None,
                    "recommendation_verbatim": "test",
                    "logic_tree": {
                        "kind": "AT_LEAST",
                        "min": 2,
                        "children": [
                            {"kind": "concept", "bitmap_id": "bm_cough"},
                            {"kind": "concept", "bitmap_id": "bm_weight"},
                            {"kind": "concept", "bitmap_id": "bm_fatigue"},
                        ],
                    },
                    "action": None,
                }
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"cough": 1, "weight": 2},
            bitmaps={
                "bm_cough": bm_cough,
                "bm_weight": bm_weight,
                "bm_fatigue": bm_fatigue,
            },
        )
        result = ev.evaluate_patient(["cough", "weight"])
        assert len(result["matched_rules"]) == 1

    def test_schema_v2_not_with_multiple_children_fails_closed(self, evaluator_factory):
        bm_a = BitMap([1])
        bm_b = BitMap([2])
        ruleset = {
            "version": "v2",
            "rules": [
                {
                    "rule_id": "r4",
                    "name": "Bad NOT",
                    "strength": "refer",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "guideline_title": "Cancer",
                    "chapter_title": None,
                    "recommendation_verbatim": "test",
                    "logic_tree": {
                        "kind": "NOT",
                        "children": [
                            {"kind": "concept", "bitmap_id": "bm_a"},
                            {"kind": "concept", "bitmap_id": "bm_b"},
                        ],
                    },
                    "action": None,
                }
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"code1": 1},
            bitmaps={"bm_a": bm_a, "bm_b": bm_b},
        )
        result = ev.evaluate_patient(["code1"])
        assert result["matched_rules"] == []


# -- Synonym set: matched_via attribution (UN-LEO-AI-093 / DI-LEO-AI-510) ----


def _make_v2_concept_rule(rule_id, bitmap_id, primary_id, seed_ids, label):
    """Compiled schema-v2 rule with a single CONCEPT logic-tree leaf."""
    return {
        "rule_id": rule_id,
        "name": label,
        "strength": "refer",
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer",
        "chapter_title": None,
        "recommendation_verbatim": f"Refer for {label}.",
        "schema_version": 2,
        "logic_tree": {
            "kind": "CONCEPT",
            "node_id": "n1",
            "bitmap_id": bitmap_id,
            "criterion": {
                "primary_concept_id": primary_id,
                "snomed_concept_id": primary_id,
                "preferred_term": label,
            },
            "seed_concept_ids": list(seed_ids),
        },
        "action": None,
    }


def test_matched_via_attributes_hit_to_specific_synonym_seed(evaluator_factory):
    """When a descendant seed matches, matched_via names that exact code."""
    bm = BitMap([2])
    rule = _make_v2_concept_rule(
        rule_id="r1",
        bitmap_id="bm1",
        primary_id="1",
        seed_ids=["1", "2"],
        label="Smoker",
    )
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"1": 1, "2": 2},
        bitmaps={"bm1": bm},
    )
    result = ev.evaluate_patient(["2"])
    assert len(result["matched_rules"]) == 1
    matched_via = result["matched_rules"][0]["matched_via"]
    assert len(matched_via) == 1
    entry = matched_via[0]
    assert entry["primary_concept_id"] == "1"
    assert entry["matched_concept_ids"] == ["2"]


def test_matched_via_omitted_when_only_primary_seed_hits(evaluator_factory):
    """matched_via is still populated for the primary seed (single-hit case)."""
    bm = BitMap([1])
    rule = _make_v2_concept_rule(
        rule_id="r1",
        bitmap_id="bm1",
        primary_id="1",
        seed_ids=["1", "2"],
        label="Smoker",
    )
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"1": 1, "2": 2},
        bitmaps={"bm1": bm},
    )
    result = ev.evaluate_patient(["1"])
    matched_via = result["matched_rules"][0]["matched_via"]
    assert matched_via == [
        {
            "kind": "CONCEPT",
            "node_id": "n1",
            "primary_concept_id": "1",
            "preferred_term": "Smoker",
            "matched_concept_ids": ["1"],
        }
    ]


def test_matched_via_lists_every_hit_when_multiple_seeds_present(evaluator_factory):
    """If two seeds both hit, both ids appear in matched_concept_ids."""
    bm = BitMap([1, 2])
    rule = _make_v2_concept_rule(
        rule_id="r1",
        bitmap_id="bm1",
        primary_id="1",
        seed_ids=["1", "2"],
        label="Smoker",
    )
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"1": 1, "2": 2},
        bitmaps={"bm1": bm},
    )
    result = ev.evaluate_patient(["1", "2"])
    matched_via = result["matched_rules"][0]["matched_via"]
    assert matched_via[0]["matched_concept_ids"] == ["1", "2"]


def test_matched_via_includes_demographic_age_sex_and_concept(evaluator_factory):
    """Firing rules report age, gender, and SNOMED hits in matched_via."""
    bm = BitMap([1])
    rule = {
        "rule_id": "r-age-sex",
        "name": "Breast rule",
        "schema_version": 2,
        "guideline_id": "NG12",
        "logic_tree": {
            "kind": "AND",
            "node_id": "root",
            "children": [
                {
                    "kind": "DEMOGRAPHIC",
                    "node_id": "age1",
                    "field": "age",
                    "operator": ">=",
                    "value": 50.0,
                    "unit": "years",
                },
                {
                    "kind": "DEMOGRAPHIC",
                    "node_id": "sex1",
                    "field": "sex",
                    "operator": "=",
                    "value": "female",
                },
                {
                    "kind": "CONCEPT",
                    "node_id": "n1",
                    "bitmap_id": "bm1",
                    "criterion": {
                        "primary_concept_id": "1",
                        "snomed_concept_id": "1",
                        "preferred_term": "Nipple discharge symptom (finding)",
                    },
                    "seed_concept_ids": ["1"],
                },
            ],
        },
    }
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"1": 1},
        bitmaps={"bm1": bm},
    )
    result = ev.evaluate_patient(["1"], patient_age=71, patient_sex="female")
    matched_via = result["matched_rules"][0]["matched_via"]
    assert matched_via[0]["kind"] == "DEMOGRAPHIC"
    assert matched_via[0]["field"] == "age"
    assert matched_via[0]["patient_value"] == 71
    assert matched_via[1]["field"] == "sex"
    assert matched_via[2]["matched_concept_ids"] == ["1"]


def test_matched_via_or_branch_excludes_non_firing_concepts(evaluator_factory):
    """Only the winning OR branch contributes concept attribution."""
    rule = {
        "rule_id": "r-or",
        "name": "OR rule",
        "schema_version": 2,
        "guideline_id": "NG12",
        "logic_tree": {
            "kind": "OR",
            "node_id": "root",
            "children": [
                {
                    "kind": "AND",
                    "node_id": "branch-a",
                    "children": [
                        {
                            "kind": "DEMOGRAPHIC",
                            "node_id": "age-a",
                            "field": "age",
                            "operator": ">=",
                            "value": 50.0,
                            "unit": "years",
                        },
                        {
                            "kind": "CONCEPT",
                            "node_id": "n-a",
                            "bitmap_id": "bm-a",
                            "criterion": {
                                "primary_concept_id": "1",
                                "snomed_concept_id": "1",
                                "preferred_term": "Breast lump",
                            },
                            "seed_concept_ids": ["1"],
                        },
                    ],
                },
                {
                    "kind": "CONCEPT",
                    "node_id": "n-b",
                    "bitmap_id": "bm-b",
                    "criterion": {
                        "primary_concept_id": "2",
                        "snomed_concept_id": "2",
                        "preferred_term": "Cough",
                    },
                    "seed_concept_ids": ["2"],
                },
            ],
        },
    }
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"1": 1, "2": 2},
        bitmaps={"bm-a": BitMap([1]), "bm-b": BitMap([2])},
    )
    result = ev.evaluate_patient(["1", "2"], patient_age=71)
    matched_via = result["matched_rules"][0]["matched_via"]
    terms = [entry.get("preferred_term") or entry.get("field") for entry in matched_via]
    assert "Breast lump" in terms
    assert "Cough" not in terms


def test_matched_via_absent_for_schema_v1_rule(evaluator_factory):
    """v1 rules have no logic_tree; matched_via is omitted entirely."""
    bm = BitMap([1])
    rule = _make_rule(
        criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}],
    )
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"443416000": 1},
        bitmaps={"bm1": bm},
    )
    result = ev.evaluate_patient(["443416000"])
    assert "matched_via" not in result["matched_rules"][0]


def test_diagnose_annotates_concept_leaf_with_matched_concept_ids(evaluator_factory):
    """The annotated_tree leaf surfaces matched_concept_ids for UI display."""
    bm = BitMap([2])
    rule = _make_v2_concept_rule(
        rule_id="r1",
        bitmap_id="bm1",
        primary_id="1",
        seed_ids=["1", "2"],
        label="Smoker",
    )
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"1": 1, "2": 2},
        bitmaps={"bm1": bm},
    )
    out = ev.diagnose("r1", ["2"])
    assert out["fires"] is True
    leaf = out["annotated_tree"]
    assert leaf["matched_concept_ids"] == ["2"]
    assert leaf["matched"] is True


def _make_sex_demographic_rule(rule_id: str = "r_sex") -> dict:
    """Build a schema-v2 rule with a DEMOGRAPHIC sex=female node."""
    return {
        "rule_id": rule_id,
        "name": "Sex-specific rule",
        "strength": "refer",
        "guideline_id": "NG151",
        "guideline_title": "Test guideline",
        "chapter_title": None,
        "recommendation_verbatim": "Refer if female",
        "schema_version": 2,
        "criteria_groups": [],
        "applies_to": [],
        "action": None,
        "logic_tree": {
            "kind": "DEMOGRAPHIC",
            "field": "sex",
            "operator": "=",
            "value": "female",
            "children": [],
        },
    }


class TestPdsGenderGate:
    """DI-9AA2CDA5 clauses (a), (b), (d), (e) -- PDS gender gating."""

    def _ruleset_with_sex_rule(self) -> dict:
        return {"version": "v1", "rules": [_make_sex_demographic_rule()]}

    def test_other_sex_sets_review_flag(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset_with_sex_rule())
        result = ev.evaluate_patient(["443416000"], patient_sex="other")
        assert result["gender_review_flag"] is True
        assert result["gender_review_reason"] == "pds_gender_unusable"
        assert result["limitation_notice"] is None

    def test_unknown_sex_sets_review_flag(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset_with_sex_rule())
        result = ev.evaluate_patient(["443416000"], patient_sex="unknown")
        assert result["gender_review_flag"] is True
        assert result["gender_review_reason"] == "pds_gender_unusable"

    def test_other_sex_counts_skipped_sex_sensitive_rules(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset_with_sex_rule())
        result = ev.evaluate_patient([], patient_sex="other")
        assert result["gender_sensitive_rules_skipped"] == 1

    def test_male_sex_returns_limitation_notice(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset_with_sex_rule())
        result = ev.evaluate_patient([], patient_sex="male")
        assert result["gender_review_flag"] is False
        assert result["gender_review_reason"] is None
        assert "reproductive anatomy" in result["limitation_notice"]

    def test_female_sex_returns_limitation_notice(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset_with_sex_rule())
        result = ev.evaluate_patient([], patient_sex="female")
        assert result["gender_review_flag"] is False
        assert "reproductive anatomy" in result["limitation_notice"]

    def test_no_sex_no_flag_no_notice(self, evaluator_factory):
        bm = BitMap([1])
        ruleset = {
            "version": "v1",
            "rules": [
                _make_rule(criteria_groups=[{"mode": "ALL", "bitmap_id": "bm1"}])
            ],
        }
        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1},
            bitmaps={"bm1": bm},
        )
        result = ev.evaluate_patient(["443416000"])
        assert result["gender_review_flag"] is False
        assert result["gender_review_reason"] is None
        assert result["limitation_notice"] is None
        assert result["gender_basis"] is None

    def test_gender_basis_pds_gender_when_sex_supplied(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset_with_sex_rule())
        result = ev.evaluate_patient([], patient_sex="female")
        assert result["gender_basis"] == "pds_gender"

    def test_gender_basis_none_when_no_sex(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset={"version": "v1", "rules": []})
        result = ev.evaluate_patient([])
        assert result["gender_basis"] is None

    def test_gender_fields_present_on_not_compiled_response(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=None)
        result = ev.evaluate_patient([], patient_sex="female")
        assert "gender_review_flag" in result
        assert "gender_basis" in result
        assert result["not_compiled"] is True

    def test_unusable_sex_skips_sex_snomed_injection(self, evaluator_factory):
        """When PDS gender is unusable, sex SNOMED codes are not injected."""
        female_snomed = "248152002"
        bm = BitMap([99])
        rule = {
            "rule_id": "r_female",
            "schema_version": 1,
            "criteria_groups": [{"mode": "ALL", "bitmap_id": "bm_female"}],
            "applies_to": [],
        }
        ev = evaluator_factory(
            current_ruleset={"version": "v1", "rules": [rule]},
            int_id_map={female_snomed: 99},
            bitmaps={"bm_female": bm},
        )
        result_binary = ev.evaluate_patient([], patient_sex="female")
        result_other = ev.evaluate_patient([], patient_sex="other")
        assert len(result_binary["matched_rules"]) == 1
        assert len(result_other["matched_rules"]) == 0


class TestAnatomyConflict:
    """DI-9AA2CDA5 clause (c) -- anatomy/gender conflict detection."""

    def _ruleset(self) -> dict:
        return {"version": "v1", "rules": []}

    def test_male_patient_with_cervix_code_sets_conflict_flag(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["71252005"], patient_sex="male")
        assert result["gender_review_flag"] is True
        assert result["gender_review_reason"] == "anatomy_conflict"
        assert result["gender_basis"] == "anatomy_evidence"

    def test_female_patient_with_prostate_code_sets_conflict_flag(
        self, evaluator_factory
    ):
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["41216001"], patient_sex="female")
        assert result["gender_review_flag"] is True
        assert result["gender_review_reason"] == "anatomy_conflict"

    def test_no_conflict_when_anatomy_matches_sex(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["71252005"], patient_sex="female")
        assert result["gender_review_flag"] is False
        assert result["gender_review_reason"] is None

    def test_no_anatomy_codes_no_inferred_conflict(self, evaluator_factory):
        """Clause (d): no anatomy evidence means no conflict flag is raised."""
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["443416000"], patient_sex="male")
        assert result["gender_review_flag"] is False
        assert result["gender_review_reason"] is None

    def test_gender_basis_anatomy_evidence_when_conflict(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["71252005"], patient_sex="male")
        assert result["gender_basis"] == "anatomy_evidence"

    def test_gender_basis_pds_gender_when_no_conflict(self, evaluator_factory):
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["443416000"], patient_sex="female")
        assert result["gender_basis"] == "pds_gender"

    def test_anatomy_conflict_overrides_limitation_notice(self, evaluator_factory):
        """When anatomy conflict fires, limitation_notice is cleared."""
        ev = evaluator_factory(current_ruleset=self._ruleset())
        result = ev.evaluate_patient(["41216001"], patient_sex="female")
        assert result["gender_review_flag"] is True
        assert result["limitation_notice"] is None


def _v2_soft_rule(
    *,
    rule_id: str = "r-soft",
    soft_qualifiers: list | None = None,
    investigation_policy: str | None = None,
    bitmap_id: str = "bm1",
) -> dict:
    criterion: dict = {
        "snomed_concept_id": "443416000",
        "preferred_term": "Vaginal discharge",
        "soft_qualifiers": soft_qualifiers or [],
    }
    return {
        "rule_id": rule_id,
        "name": "Soft gate rule",
        "strength": "consider",
        "schema_version": 2,
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer",
        "chapter_title": None,
        "recommendation_verbatim": "consider ultrasound",
        "investigation_policy": investigation_policy,
        "logic_tree": {
            "kind": "concept",
            "bitmap_id": bitmap_id,
            "criterion": criterion,
            "seed_concept_ids": ["443416000"],
        },
        "action": None,
        "actions": [],
    }


class TestSoftQualifiersAndFitStatus:
    """DI-C136E4B7 / DI-55CCC312: evaluator uses the shared resolver."""

    def _ev(self, evaluator_factory, rules, bitmaps=None):
        return evaluator_factory(
            current_ruleset={"version": "v-soft", "rules": rules},
            int_id_map={"443416000": 1},
            bitmaps=bitmaps or {"bm1": BitMap([1])},
        )

    def test_hard_facts_plus_not_confirmed_soft_still_match(self, evaluator_factory):
        """DI-C136E4B7: Hard facts plus a not-confirmed soft word still match."""
        ev = self._ev(
            evaluator_factory,
            [
                _v2_soft_rule(
                    soft_qualifiers=[{"kind": "unexplained", "enforcement": "soft"}]
                )
            ],
        )
        result = ev.evaluate_patient(
            ["443416000"],
            letter_text="vaginal discharge- 10/7 yellowish",
        )
        assert len(result["matched_rules"]) == 1
        assert result["matched_rules"][0]["unverified_qualifiers"] == ["unexplained"]

    def test_contradicted_soft_word_does_not_match(self, evaluator_factory):
        """DI-C136E4B7: Hard facts plus a contradicted soft word do not match."""
        from datetime import datetime, timezone

        ev = self._ev(
            evaluator_factory,
            [
                _v2_soft_rule(
                    soft_qualifiers=[
                        {
                            "kind": "first_presentation",
                            "enforcement": "soft",
                            "concept_id": "443416000",
                            "max_occurrences": 1,
                            "within_days": 365,
                        }
                    ]
                )
            ],
        )
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        result = ev.evaluate_patient(
            ["443416000"],
            letter_text="",
            concept_occurrences={
                "443416000": [
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 3, 1, tzinfo=timezone.utc),
                ]
            },
            evaluation_time=now,
        )
        assert result["matched_rules"] == []

    def test_hard_enforcement_not_confirmed_does_not_match(self, evaluator_factory):
        """DI-C136E4B7: Hard enforcement plus a not-confirmed word does not match."""
        ev = self._ev(
            evaluator_factory,
            [
                _v2_soft_rule(
                    soft_qualifiers=[{"kind": "unexplained", "enforcement": "hard"}]
                )
            ],
        )
        result = ev.evaluate_patient(["443416000"], letter_text="")
        assert result["matched_rules"] == []

    def test_fit_required_missing_without_kit_or_result(self, evaluator_factory):
        """DI-55CCC312: FIT required plus no kit or result is missing."""
        ev = self._ev(
            evaluator_factory,
            [_v2_soft_rule(investigation_policy="required")],
        )
        result = ev.evaluate_patient(["443416000"])
        assert result["matched_rules"][0]["investigation_status"] == "missing"

    def test_fit_not_required_is_exempt_without_fit(self, evaluator_factory):
        """DI-55CCC312: FIT not_required is exempt even if no FIT is on the record."""
        ev = self._ev(
            evaluator_factory,
            [_v2_soft_rule(investigation_policy="not_required")],
        )
        result = ev.evaluate_patient(["443416000"])
        assert result["matched_rules"][0]["investigation_status"] == "exempt"

    def test_required_and_not_required_both_match_is_exempt(self, evaluator_factory):
        """DI-55CCC312: When required and not_required both match, status is exempt."""
        ev = self._ev(
            evaluator_factory,
            [
                _v2_soft_rule(rule_id="r-req", investigation_policy="required"),
                _v2_soft_rule(rule_id="r-mass", investigation_policy="not_required"),
            ],
        )
        result = ev.evaluate_patient(["443416000"])
        assert {m["rule_id"] for m in result["matched_rules"]} == {"r-req", "r-mass"}
        assert result["investigation_status"] == "exempt"
        assert all(
            m["investigation_status"] == "exempt" for m in result["matched_rules"]
        )


def test_excluded_id_on_record_blocks_the_concept_leaf(evaluator_factory) -> None:
    """A leaf that excludes a code must not fire when that code is present."""
    bm = BitMap([1])
    rule = _make_v2_concept_rule(
        rule_id="r-mass",
        bitmap_id="bm1",
        primary_id="74285003",
        seed_ids=["74285003"],
        label="Pelvic mass",
    )
    rule["logic_tree"]["criterion"]["excluded_concept_ids"] = ["65576009"]
    ev = evaluator_factory(
        current_ruleset={"version": "v1", "rules": [rule]},
        int_id_map={"74285003": 1, "65576009": 2},
        bitmaps={"bm1": bm},
    )
    hit = ev.evaluate_patient(["74285003"])
    assert len(hit["matched_rules"]) == 1
    blocked = ev.evaluate_patient(["74285003", "65576009"])
    assert blocked["matched_rules"] == []


def test_excluded_ids_on_record_are_the_overlap() -> None:
    from services.terminology_api.app.services.guideline_evaluator import (
        _excluded_ids_on_record,
    )

    tree = {
        "kind": "OR",
        "children": [
            {
                "kind": "concept",
                "criterion": {
                    "snomed_concept_id": "74285003",
                    "excluded_concept_ids": ["65576009", "11314008"],
                },
            }
        ],
    }
    assert _excluded_ids_on_record(tree, ["74285003", "65576009"]) == ["65576009"]
    assert _excluded_ids_on_record(tree, ["74285003"]) == []
