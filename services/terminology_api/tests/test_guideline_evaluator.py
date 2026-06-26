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
    store.get_int_ids_bulk.side_effect = (
        lambda cids: {c: int_id_map[c] for c in cids if c in int_id_map}
    )
    store.get_bitmaps_bulk.side_effect = (
        lambda bids: {b: bitmaps[b] for b in bids if b in bitmaps}
    )
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
