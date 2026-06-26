"""Unit tests for ALLERGY leaf evaluation.

Atlas trace: VT-B60E3046
"""

import pytest

from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator


class TestAllergyMatches:
    def _eval(self, node, facts):
        return GuidelineEvaluator._allergy_matches(node, facts)

    def test_active_penicillin_matches(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        facts = [{"substance_concept_id": "764146007", "status": "active",
                  "source_ids": ["enc-2"]}]
        matched, reason, src = self._eval(node, facts)
        assert matched is True
        assert src == ["enc-2"]

    def test_resolved_allergy_does_not_match(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        facts = [{"substance_concept_id": "764146007", "status": "resolved"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_nkda_does_not_match_and_reason_says_nkda(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        facts = [{"substance_concept_id": "nkda", "status": "nkda"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
        assert "no known drug allergies" in reason.lower()

    def test_unknown_allergy_fails_closed(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        facts = [{"substance_concept_id": "764146007", "status": "unknown"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False

    def test_empty_allergy_list_fails_closed_with_distinct_reason(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        matched, reason, _ = self._eval(node, [])
        assert matched is False
        assert "no allergy information" in reason.lower()

    def test_class_level_match(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007",
                "allergy_class": "penicillin"}
        facts = [{"substance_concept_id": "other", "status": "active",
                  "allergy_class": "penicillin", "source_ids": ["enc-3"]}]
        matched, reason, src = self._eval(node, facts)
        assert matched is True
        assert src == ["enc-3"]

    def test_wrong_concept_and_no_class_does_not_match(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        facts = [{"substance_concept_id": "999", "status": "active"}]
        matched, reason, _ = self._eval(node, facts)
        assert matched is False
