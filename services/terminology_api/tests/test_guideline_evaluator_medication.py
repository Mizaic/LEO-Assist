"""Unit tests for MEDICATION leaf evaluation.

Atlas trace: VT-B60E3046
"""

import pytest

from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator


class TestMedicationMatches:
    def _eval(self, node, facts):
        return GuidelineEvaluator._medication_matches(node, facts)

    def test_active_nsaid_matches_nsaid_leaf(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "NSAID", "status": "active", "source_ids": ["enc-1"]}]
        matched, reason, source_ids = self._eval(node, facts)
        assert matched is True
        assert source_ids == ["enc-1"]

    def test_stopped_nsaid_does_not_match(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "NSAID", "status": "stopped"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
        assert "stopped" in reason.lower() or "fail closed" in reason.lower()

    def test_planned_nsaid_does_not_match(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "NSAID", "status": "planned"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_historical_nsaid_does_not_match(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "NSAID", "status": "historical"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_unknown_status_fails_closed(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "NSAID", "status": "unknown"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
        assert "fail closed" in reason.lower()

    def test_empty_medication_list_fails_closed(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        matched, reason, _ = self._eval(node, [])
        assert matched is False
        assert "fail closed" in reason.lower()

    def test_wrong_drug_class_does_not_match(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "PPI", "status": "active"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_concept_id_must_match_when_present(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID", "concept_id": "111"}
        facts = [{"drug_class": "NSAID", "status": "active", "concept_id": "222"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_concept_id_matches_when_equal(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID", "concept_id": "111"}
        facts = [{"drug_class": "NSAID", "status": "active",
                  "concept_id": "111", "source_ids": ["enc-x"]}]
        matched, reason, src = self._eval(node, facts)
        assert matched is True
        assert src == ["enc-x"]
