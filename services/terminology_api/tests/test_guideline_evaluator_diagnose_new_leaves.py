"""Unit tests for per-leaf diagnostic entries for new leaf kinds.

Atlas trace: VT-13B27C99
"""

import pytest

from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator


class TestAnnotateLogicTreeNewLeaves:
    """_annotate_logic_tree produces correct per-leaf diagnostic entries."""

    def _annotate(self, node, active_medications=None, allergies=None,
                  treatment_history=None):
        from unittest.mock import MagicMock
        from pyroaring import BitMap
        ev = GuidelineEvaluator.__new__(GuidelineEvaluator)
        ev._store = MagicMock()
        bm = BitMap()
        return ev._annotate_logic_tree(
            node, bm, None, None,
            active_medications=active_medications or [],
            allergies=allergies or [],
            treatment_history=treatment_history or [],
        )

    def test_medication_leaf_entry_has_required_fields(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        result = self._annotate(
            node,
            active_medications=[{"drug_class": "NSAID", "status": "active",
                                  "source_ids": ["enc-x"]}],
        )
        assert result is not None
        assert result["kind"] == "MEDICATION"
        assert "matched" in result
        assert "reason" in result
        assert "source_ids" in result

    def test_medication_leaf_matched_agrees_with_evaluate(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        facts = [{"drug_class": "NSAID", "status": "active"}]
        annotated = self._annotate(node, active_medications=facts)
        direct_matched, _, _ = GuidelineEvaluator._medication_matches(node, facts)
        assert annotated["matched"] == direct_matched

    def test_allergy_leaf_entry_has_required_fields(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        result = self._annotate(
            node,
            allergies=[{"substance_concept_id": "764146007", "status": "active",
                         "source_ids": ["enc-y"]}],
        )
        assert result is not None
        assert result["kind"] == "ALLERGY"
        assert "matched" in result
        assert "reason" in result
        assert "source_ids" in result

    def test_allergy_leaf_matched_agrees_with_evaluate(self):
        node = {"kind": "ALLERGY", "substance_concept_id": "764146007"}
        facts = [{"substance_concept_id": "764146007", "status": "active"}]
        annotated = self._annotate(node, allergies=facts)
        direct_matched, _, _ = GuidelineEvaluator._allergy_matches(node, facts)
        assert annotated["matched"] == direct_matched

    def test_treatment_history_leaf_entry_has_required_fields(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        result = self._annotate(
            node,
            treatment_history=[{"treatment_class": "PPI", "outcome": "failed",
                                  "source_ids": ["enc-z"]}],
        )
        assert result is not None
        assert result["kind"] == "TREATMENT_HISTORY"
        assert "matched" in result
        assert "reason" in result
        assert "source_ids" in result

    def test_treatment_leaf_matched_agrees_with_evaluate(self):
        node = {"kind": "TREATMENT_HISTORY", "treatment_class": "PPI"}
        facts = [{"treatment_class": "PPI", "outcome": "failed"}]
        annotated = self._annotate(node, treatment_history=facts)
        direct_matched, _, _ = GuidelineEvaluator._treatment_history_matches(
            node, facts
        )
        assert annotated["matched"] == direct_matched

    def test_no_match_reason_is_non_empty(self):
        node = {"kind": "MEDICATION", "drug_class": "NSAID"}
        result = self._annotate(node, active_medications=[])
        assert result["matched"] is False
        assert result["reason"]

    def test_existing_concept_leaf_still_annotates(self):
        from unittest.mock import MagicMock
        from pyroaring import BitMap
        ev = GuidelineEvaluator.__new__(GuidelineEvaluator)
        mock_bm = BitMap([1, 2])
        ev._store = MagicMock()
        ev._store.get_bitmap.return_value = mock_bm
        node = {"kind": "CONCEPT", "bitmap_id": "bm-001",
                "seed_concept_ids": [], "criterion": {}}
        patient_bm = BitMap([3, 4])
        result = ev._annotate_logic_tree(node, patient_bm, None, None)
        assert result is not None
        assert result["kind"] == "CONCEPT"
        assert "matched" in result
