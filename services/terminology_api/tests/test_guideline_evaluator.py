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
    int_id_map = int_id_map or {}
    store.get_int_id.side_effect = lambda cid: int_id_map.get(cid)
    bitmaps = bitmaps or {}
    store.get_bitmap.side_effect = lambda bid: bitmaps.get(bid)
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


class TestRequiredCriteriaMatching:
    """Rule matches when all required concepts are in the patient's code set."""

    def test_rule_matches_when_required_concept_present(self, evaluator_factory):
        """A rule with one PRESENT criterion matches when patient has that code."""
        req_bm = BitMap([1])
        req_id = "req_abc"

        ruleset = {
            "version": "v1",
            "rules": [{
                "rule_id": "r1",
                "name": "Test rule",
                "strength": "refer",
                "guideline_id": "NG151",
                "guideline_title": "Bowel cancer",
                "recommendation_verbatim": "Refer for rectal bleeding",
                "req_all_bitmap_id": req_id,
                "forbid_bitmap_id": None,
            }]
        }

        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1},
            bitmaps={req_id: req_bm},
        )
        result = ev.evaluate_patient(["443416000"])

        assert len(result["matched_rules"]) == 1
        assert result["matched_rules"][0]["rule_id"] == "r1"

    def test_rule_does_not_match_when_required_concept_missing(self, evaluator_factory):
        """A rule does not match when the patient is missing a required concept."""
        req_bm = BitMap([1])
        req_id = "req_abc"

        ruleset = {
            "version": "v1",
            "rules": [{
                "rule_id": "r1",
                "name": "Test rule",
                "strength": "refer",
                "guideline_id": "NG151",
                "guideline_title": "Bowel cancer",
                "recommendation_verbatim": "Refer for rectal bleeding",
                "req_all_bitmap_id": req_id,
                "forbid_bitmap_id": None,
            }]
        }

        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"999999": 2},
            bitmaps={req_id: req_bm},
        )
        result = ev.evaluate_patient(["999999"])

        assert result["matched_rules"] == []


class TestForbiddenCriteriaExclusion:
    """Rule does not match when patient has a forbidden concept."""

    def test_rule_excluded_when_forbidden_concept_present(self, evaluator_factory):
        """Rule is excluded when any forbidden concept appears in patient codes."""
        req_bm = BitMap([1])
        forbid_bm = BitMap([2])
        req_id = "req_abc"
        forbid_id = "forbid_abc"

        ruleset = {
            "version": "v1",
            "rules": [{
                "rule_id": "r1",
                "name": "Test rule",
                "strength": "refer",
                "guideline_id": "NG151",
                "guideline_title": "Bowel cancer",
                "recommendation_verbatim": "Refer if no known bowel disease",
                "req_all_bitmap_id": req_id,
                "forbid_bitmap_id": forbid_id,
            }]
        }

        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1, "bowel_disease": 2},
            bitmaps={req_id: req_bm, forbid_id: forbid_bm},
        )
        result = ev.evaluate_patient(["443416000", "bowel_disease"])

        assert result["matched_rules"] == [], (
            "Rule should be excluded when patient has a forbidden concept"
        )

    def test_rule_matches_when_patient_lacks_forbidden_concept(self, evaluator_factory):
        """Rule matches when patient has required codes but NOT forbidden codes."""
        req_bm = BitMap([1])
        forbid_bm = BitMap([2])
        req_id = "req_abc"
        forbid_id = "forbid_abc"

        ruleset = {
            "version": "v1",
            "rules": [{
                "rule_id": "r1",
                "name": "Test rule",
                "strength": "refer",
                "guideline_id": "NG151",
                "guideline_title": "Bowel cancer",
                "recommendation_verbatim": "Refer if no known bowel disease",
                "req_all_bitmap_id": req_id,
                "forbid_bitmap_id": forbid_id,
            }]
        }

        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1},
            bitmaps={req_id: req_bm, forbid_id: forbid_bm},
        )
        result = ev.evaluate_patient(["443416000"])

        assert len(result["matched_rules"]) == 1


class TestUnknownCodes:
    """Unknown patient codes are silently skipped."""

    def test_unknown_patient_codes_are_skipped(self, evaluator_factory):
        """Concept IDs not in the int_id store are excluded from the patient bitmap."""
        req_bm = BitMap([1])
        req_id = "req_abc"

        ruleset = {
            "version": "v1",
            "rules": [{
                "rule_id": "r1",
                "name": "Test rule",
                "strength": "refer",
                "guideline_id": "NG151",
                "guideline_title": "Bowel cancer",
                "recommendation_verbatim": "Test",
                "req_all_bitmap_id": req_id,
                "forbid_bitmap_id": None,
            }]
        }

        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={},
            bitmaps={req_id: req_bm},
        )
        result = ev.evaluate_patient(["UNKNOWN_CODE"])

        assert result["matched_rules"] == []


class TestPathwayFilter:
    """pathway_filter restricts evaluation to a specific guideline."""

    def test_pathway_filter_excludes_other_guidelines(self, evaluator_factory):
        """Rules for other guidelines are excluded when pathway_filter is set."""
        req_bm = BitMap([1])
        req_id = "req_abc"

        ruleset = {
            "version": "v1",
            "rules": [{
                "rule_id": "r1",
                "name": "Test rule",
                "strength": "refer",
                "guideline_id": "CG89",
                "guideline_title": "Other guideline",
                "recommendation_verbatim": "Test",
                "req_all_bitmap_id": req_id,
                "forbid_bitmap_id": None,
            }]
        }

        ev = evaluator_factory(
            current_ruleset=ruleset,
            int_id_map={"443416000": 1},
            bitmaps={req_id: req_bm},
        )
        result = ev.evaluate_patient(["443416000"], pathway_filter="NG151")

        assert result["matched_rules"] == []
