"""VT-LEO-AI-169 -- per-rule diagnostic uses the bitmap evaluator.

Verifies that GuidelineEvaluator.diagnose() returns an annotated
logic_tree whose verdict agrees with the production firing decision
(evaluate_patient) for the same inputs, so the test-patient diagnostic
view in the UI can never disagree with the live ruleset.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_evaluator import (
    GuidelineEvaluator,
)


def _make_store(*, ruleset, int_ids, bitmaps):
    store = MagicMock(spec=BitmapStore)
    store.get_current_ruleset.return_value = ruleset
    store.get_ruleset.return_value = ruleset
    # Single-key accessors (legacy paths)
    store.get_int_id.side_effect = lambda cid: int_ids.get(cid)
    store.get_bitmap.side_effect = lambda bid: bitmaps.get(bid)
    # Bulk accessors used by evaluate_patient and diagnose
    store.get_int_ids_bulk.side_effect = (
        lambda cids: {c: int_ids[c] for c in cids if c in int_ids}
    )
    store.get_bitmaps_bulk.side_effect = (
        lambda bids: {b: bitmaps[b] for b in bids if b in bitmaps}
    )
    return store


def _v2_rule():
    """Schema-v2 rule:
        AND(
            DEMOGRAPHIC age >= 40,
            OR(CONCEPT cough, CONCEPT dyspnea),
        )
    Bitmaps include the SNOMED descendants of each criterion -- that
    is the WHOLE point of using the production evaluator: a patient
    coded with a descendant of "Cough (finding)" should still match,
    which the previous client-side flat-list could never see.
    """
    return {
        "rule_id": "r1",
        "name": "Lung cancer red flags",
        "schema_version": 2,
        "guideline_id": "NG12",
        "logic_tree": {
            "kind": "AND",
            "node_id": "n0",
            "children": [
                {
                    "kind": "DEMOGRAPHIC",
                    "node_id": "n1",
                    "field": "age",
                    "operator": ">=",
                    "value": 40,
                    "unit": "years",
                },
                {
                    "kind": "OR",
                    "node_id": "n2",
                    "children": [
                        {
                            "kind": "CONCEPT",
                            "node_id": "n3",
                            "bitmap_id": "bm:cough",
                            "criterion": {
                                "snomed_concept_id": "49727002",
                                "preferred_term": "Cough (finding)",
                            },
                        },
                        {
                            "kind": "CONCEPT",
                            "node_id": "n4",
                            "bitmap_id": "bm:dyspnea",
                            "criterion": {
                                "snomed_concept_id": "267036007",
                                "preferred_term": "Dyspnea (finding)",
                            },
                        },
                    ],
                },
            ],
        },
    }


def _ev_for(patient_age, patient_codes):
    ruleset = {"version": "v1", "rules": [_v2_rule()]}
    bitmaps = {
        # The compiled bitmaps include the SNOMED descendant closure --
        # we mimic that by putting the descendant int id in the bitmap.
        "bm:cough": BitMap([100, 101]),
        "bm:dyspnea": BitMap([200]),
    }
    int_ids = {
        # 49727002 maps to 100; the patient might present with the
        # descendant 161635002 which compiles down to 101.
        "49727002": 100,
        "161635002": 101,
        "267036007": 200,
    }
    store = _make_store(ruleset=ruleset, int_ids=int_ids, bitmaps=bitmaps)
    return GuidelineEvaluator(store=store)


class TestDiagnoseAgreesWithEvaluate:
    def test_young_patient_with_cough_descendant_does_not_fire(self):
        """Age 29 fails the demographic gate, so the rule must not fire.

        The diagnostic must agree -- the AND root is not matched,
        the demographic leaf is unsatisfied, and the OR child IS
        satisfied because the patient has the descendant Cough code.
        """
        ev = _ev_for(patient_age=29, patient_codes=["161635002"])
        diag = ev.diagnose("r1", ["161635002"], patient_age=29)
        live = ev.evaluate_patient(["161635002"], patient_age=29)

        assert diag["fires"] is False
        assert diag["fires"] == any(
            r["rule_id"] == "r1" for r in live["matched_rules"]
        )

        tree = diag["annotated_tree"]
        assert tree["kind"] == "AND"
        assert tree["matched"] is False
        assert tree["matched_count"] == 1
        assert tree["total_count"] == 2

        kinds = {child["kind"]: child for child in tree["children"]}
        demographic = kinds["DEMOGRAPHIC"]
        assert demographic["matched"] is False

        or_node = kinds["OR"]
        assert or_node["matched"] is True
        assert or_node["matched_count"] == 1
        cough = or_node["children"][0]
        assert cough["matched"] is True
        assert cough["criterion"]["snomed_concept_id"] == "49727002"

    def test_eligible_patient_with_cough_fires_rule(self):
        ev = _ev_for(patient_age=55, patient_codes=["161635002"])
        diag = ev.diagnose("r1", ["161635002"], patient_age=55)
        live = ev.evaluate_patient(["161635002"], patient_age=55)

        assert diag["fires"] is True
        assert any(r["rule_id"] == "r1" for r in live["matched_rules"])
        assert diag["annotated_tree"]["matched"] is True

    def test_diagnose_marks_rule_not_found(self):
        # Diagnose now returns a structured payload (rule_found=False
        # plus the active version) instead of None so the UI can tell a
        # missing rule_id apart from a missing ruleset.
        ev = _ev_for(patient_age=55, patient_codes=["161635002"])
        result = ev.diagnose("rule:does-not-exist", ["161635002"])
        assert result is not None
        assert result["rule_found"] is False
        assert result["not_compiled"] is False
        assert result["fires"] is False

    def test_diagnose_marks_not_compiled_when_no_active_ruleset(self):
        # When no ruleset is loaded the diagnose response carries
        # not_compiled=True + a recompile_hint so the UI can render a
        # one-click "Compile now" banner instead of a vague error.
        store = MagicMock(spec=BitmapStore)
        store.get_current_ruleset.return_value = None
        ev = GuidelineEvaluator(store=store)
        result = ev.diagnose("r1", ["49727002"], patient_age=70)
        assert result is not None
        assert result["not_compiled"] is True
        assert result["rule_found"] is False
        assert result["fires"] is False
        assert "compile" in (result.get("recompile_hint") or "").lower()

    def test_at_least_node_reports_matched_count_and_threshold(self):
        ruleset = {
            "version": "v1",
            "rules": [
                {
                    "rule_id": "r-at-least",
                    "name": "AT_LEAST 2 of 3 symptoms",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "logic_tree": {
                        "kind": "AT_LEAST",
                        "node_id": "n0",
                        "min": 2,
                        "children": [
                            {
                                "kind": "CONCEPT",
                                "node_id": f"n{i}",
                                "bitmap_id": f"bm:s{i}",
                                "criterion": {
                                    "snomed_concept_id": f"sym{i}",
                                    "preferred_term": f"Symptom {i}",
                                },
                            }
                            for i in (1, 2, 3)
                        ],
                    },
                }
            ],
        }
        bitmaps = {
            "bm:s1": BitMap([1]),
            "bm:s2": BitMap([2]),
            "bm:s3": BitMap([3]),
        }
        int_ids = {"sym1": 1, "sym2": 2, "sym3": 3}
        store = _make_store(ruleset=ruleset, int_ids=int_ids, bitmaps=bitmaps)
        ev = GuidelineEvaluator(store=store)

        # Patient has only sym1 -- the AT_LEAST 2 group must not be
        # matched but its matched_count must be 1 of 3.
        diag = ev.diagnose("r-at-least", ["sym1"])
        tree = diag["annotated_tree"]
        assert tree["kind"] == "AT_LEAST"
        assert tree["matched"] is False
        assert tree["matched_count"] == 1
        assert tree["total_count"] == 3
        assert tree["min"] == 2

        # Patient has sym1 + sym3 -- now matched is True with
        # matched_count == 2 (the threshold).
        diag2 = ev.diagnose("r-at-least", ["sym1", "sym3"])
        tree2 = diag2["annotated_tree"]
        assert tree2["matched"] is True
        assert tree2["matched_count"] == 2

    def test_missing_bitmap_marks_concept_node_and_does_not_match(self):
        ruleset = {
            "version": "v1",
            "rules": [
                {
                    "rule_id": "r-missing",
                    "name": "Single concept rule",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "logic_tree": {
                        "kind": "AND",
                        "node_id": "n0",
                        "children": [
                            {
                                "kind": "CONCEPT",
                                "node_id": "n1",
                                "bitmap_id": "bm:missing",
                                "criterion": {
                                    "snomed_concept_id": "sym1",
                                    "preferred_term": "Symptom",
                                },
                            }
                        ],
                    },
                }
            ],
        }
        store = _make_store(ruleset=ruleset, int_ids={"sym1": 1}, bitmaps={})
        ev = GuidelineEvaluator(store=store)
        diag = ev.diagnose("r-missing", ["sym1"])
        leaf = diag["annotated_tree"]["children"][0]
        assert leaf["matched"] is False
        assert leaf["missing_bitmap"] is True


class TestDiagnoseSchemaV1:
    def test_v1_rule_renders_synthetic_tree_with_per_group_match(self):
        ruleset = {
            "version": "v1",
            "rules": [
                {
                    "rule_id": "r-v1",
                    "name": "Legacy v1 rule",
                    "guideline_id": "NG12",
                    "schema_version": 1,
                    "applies_to": [
                        {
                            "concept_id": "424144002",
                            "operator": ">=",
                            "value": 40,
                        }
                    ],
                    "criteria_groups": [
                        {"mode": "ANY", "bitmap_id": "bm:symptoms"}
                    ],
                }
            ],
        }
        bitmaps = {"bm:symptoms": BitMap([1, 2, 3])}
        store = _make_store(
            ruleset=ruleset, int_ids={"sym1": 1}, bitmaps=bitmaps
        )
        ev = GuidelineEvaluator(store=store)

        diag = ev.diagnose("r-v1", ["sym1"], patient_age=55)
        tree = diag["annotated_tree"]
        assert diag["fires"] is True
        assert tree["matched"] is True
        kinds = [c["kind"] for c in tree["children"]]
        assert "DEMOGRAPHIC" in kinds
        assert "CONCEPT_GROUP" in kinds


class TestDiagnoseRebindsEditedRules:
    """Pin the rebind behaviour for rules that have been edited.

    Every rule edit appends ``:edit:<8 hex>`` to the predecessor id (see
    ``services/api/app/services/guidance_rule_edit.py``). The compiled
    bitmap only carries the head of the SUPERSEDES chain, so a saved
    test patient's ``ExpectedSBAR.matched_rule_ids`` (or
    ``EXPECTED_RESULT.fires``) can pin a stale id. Diagnose must fall
    back to the latest rule whose stem matches, rather than 404 with
    "rule not present in the active ruleset".
    """

    _BASE = "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13"

    def _ruleset_with_edited_rule(self, active_id: str) -> dict:
        return {
            "version": "v1",
            "rules": [
                {
                    "rule_id": active_id,
                    "name": "NG12 mesothelioma chest X-ray",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "logic_tree": {
                        "kind": "CONCEPT",
                        "node_id": "n0",
                        "bitmap_id": "bm:cough",
                        "criterion": {
                            "snomed_concept_id": "49727002",
                            "preferred_term": "Cough (finding)",
                        },
                    },
                }
            ],
        }

    def test_diagnose_rebinds_to_edited_rule_when_literal_id_missing(self):
        active_id = f"{self._BASE}:edit:newhash"
        saved_id = f"{self._BASE}:edit:dd11e8d3:edit:a0b74f59"
        store = _make_store(
            ruleset=self._ruleset_with_edited_rule(active_id),
            int_ids={"49727002": 1},
            bitmaps={"bm:cough": BitMap([1])},
        )
        ev = GuidelineEvaluator(store=store)
        result = ev.diagnose(saved_id, ["49727002"])
        assert result is not None
        assert result["rule_found"] is True
        assert result["fires"] is True
        # The response carries the actually-diagnosed rule_id so the UI
        # can label "matched as <X>" instead of repeating the stale id.
        assert result["rule_id"] == active_id
        assert result["requested_rule_id"] == saved_id
        assert result["rebound_from"] == saved_id
        assert active_id in (result.get("rebind_reason") or "")

    def test_diagnose_returns_not_found_when_no_stem_match(self):
        active_id = "rule:OTHER:v1:CH001:SEC000:R001:abc"
        saved_id = f"{self._BASE}:edit:dd11e8d3:edit:a0b74f59"
        store = _make_store(
            ruleset=self._ruleset_with_edited_rule(active_id),
            int_ids={"49727002": 1},
            bitmaps={"bm:cough": BitMap([1])},
        )
        ev = GuidelineEvaluator(store=store)
        result = ev.diagnose(saved_id, ["49727002"])
        assert result is not None
        assert result["rule_found"] is False
        assert result["fires"] is False
        assert "not present" in (result.get("message") or "").lower()

    def test_diagnose_picks_latest_descendant_when_multiple_stem_matches(self):
        """When several rules share the same stem (which can happen
        transiently if a compile pulls in two edits), diagnose picks the
        longest id -- that is the most-edited variant, i.e. the latest
        descendant.
        """
        one_edit = f"{self._BASE}:edit:dd11e8d3"
        two_edits = f"{self._BASE}:edit:dd11e8d3:edit:a0b74f59"
        ruleset = {
            "version": "v1",
            "rules": [
                {
                    "rule_id": one_edit,
                    "name": "NG12 mesothelioma chest X-ray (edit 1)",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "logic_tree": {
                        "kind": "CONCEPT",
                        "node_id": "n0",
                        "bitmap_id": "bm:cough",
                        "criterion": {
                            "snomed_concept_id": "49727002",
                            "preferred_term": "Cough (finding)",
                        },
                    },
                },
                {
                    "rule_id": two_edits,
                    "name": "NG12 mesothelioma chest X-ray (edit 2)",
                    "schema_version": 2,
                    "guideline_id": "NG12",
                    "logic_tree": {
                        "kind": "CONCEPT",
                        "node_id": "n0",
                        "bitmap_id": "bm:cough",
                        "criterion": {
                            "snomed_concept_id": "49727002",
                            "preferred_term": "Cough (finding)",
                        },
                    },
                },
            ],
        }
        store = _make_store(
            ruleset=ruleset,
            int_ids={"49727002": 1},
            bitmaps={"bm:cough": BitMap([1])},
        )
        ev = GuidelineEvaluator(store=store)
        result = ev.diagnose(self._BASE, ["49727002"])
        assert result is not None
        assert result["rule_found"] is True
        assert result["rule_id"] == two_edits
