"""Unit tests for compiler support for MEDICATION, ALLERGY, and TREATMENT_HISTORY leaves.

Atlas trace: VT-6DB2FB89
"""

import pytest

from services.terminology_api.app.services.guideline_compiler import GuidelineCompiler


class TestCompileMedicationLeaf:
    def test_valid_leaf_compiles(self):
        node = {"kind": "medication", "drug_class": "NSAID", "term": "naproxen"}
        result = GuidelineCompiler._compile_medication_leaf(node)
        assert result is not None
        assert result["kind"] == "MEDICATION"
        assert result["drug_class"] == "NSAID"

    def test_missing_drug_class_returns_none(self):
        node = {"kind": "medication", "drug_class": ""}
        result = GuidelineCompiler._compile_medication_leaf(node)
        assert result is None

    def test_absent_drug_class_returns_none(self):
        node = {"kind": "medication"}
        result = GuidelineCompiler._compile_medication_leaf(node)
        assert result is None

    def test_concept_id_is_preserved(self):
        node = {"kind": "medication", "drug_class": "PPI", "concept_id": "372525000"}
        result = GuidelineCompiler._compile_medication_leaf(node)
        assert result["concept_id"] == "372525000"


class TestCompileAllergyLeaf:
    def test_valid_leaf_compiles(self):
        node = {"kind": "allergy", "substance_concept_id": "764146007", "term": "penicillin"}
        result = GuidelineCompiler._compile_allergy_leaf(node)
        assert result is not None
        assert result["kind"] == "ALLERGY"
        assert result["substance_concept_id"] == "764146007"

    def test_missing_substance_concept_id_returns_none(self):
        node = {"kind": "allergy", "substance_concept_id": ""}
        result = GuidelineCompiler._compile_allergy_leaf(node)
        assert result is None

    def test_absent_substance_concept_id_returns_none(self):
        node = {"kind": "allergy"}
        result = GuidelineCompiler._compile_allergy_leaf(node)
        assert result is None

    def test_allergy_class_is_preserved(self):
        node = {"kind": "allergy", "substance_concept_id": "764146007",
                "allergy_class": "penicillin"}
        result = GuidelineCompiler._compile_allergy_leaf(node)
        assert result["allergy_class"] == "penicillin"


class TestCompileTreatmentHistoryLeaf:
    def test_valid_leaf_compiles(self):
        node = {"kind": "treatment_history", "treatment_class": "PPI"}
        result = GuidelineCompiler._compile_treatment_history_leaf(node)
        assert result is not None
        assert result["kind"] == "TREATMENT_HISTORY"
        assert result["treatment_class"] == "PPI"

    def test_missing_treatment_class_returns_none(self):
        node = {"kind": "treatment_history", "treatment_class": ""}
        result = GuidelineCompiler._compile_treatment_history_leaf(node)
        assert result is None

    def test_absent_treatment_class_returns_none(self):
        node = {"kind": "treatment_history"}
        result = GuidelineCompiler._compile_treatment_history_leaf(node)
        assert result is None

    def test_min_duration_days_is_preserved(self):
        node = {"kind": "treatment_history", "treatment_class": "PPI",
                "min_duration_days": 28}
        result = GuidelineCompiler._compile_treatment_history_leaf(node)
        assert result["min_duration_days"] == 28

    def test_invalid_min_duration_days_returns_none(self):
        node = {"kind": "treatment_history", "treatment_class": "PPI",
                "min_duration_days": 0}
        result = GuidelineCompiler._compile_treatment_history_leaf(node)
        assert result is None
