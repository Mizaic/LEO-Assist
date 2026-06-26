"""Unit tests for MedicationLeaf, AllergyLeaf, and TreatmentHistoryLeaf.

Atlas trace: VT-6DB2FB89 (compiler), VT-B60E3046 (evaluator)
"""

import pytest
from pydantic import ValidationError

from libs.guidance_schema.medication_allergy_treatment_leaves import (
    AllergyLeaf,
    AllergyLeafValidationError,
    MedicationLeaf,
    MedicationLeafValidationError,
    TreatmentHistoryLeaf,
    TreatmentHistoryLeafValidationError,
)


class TestMedicationLeaf:
    def test_valid_leaf_parses(self):
        leaf = MedicationLeaf(kind="MEDICATION", drug_class="NSAID")
        assert leaf.drug_class == "NSAID"
        assert leaf.concept_id is None

    def test_valid_leaf_with_concept_id(self):
        leaf = MedicationLeaf(kind="MEDICATION", drug_class="NSAID",
                               concept_id="372665008")
        assert leaf.concept_id == "372665008"

    def test_missing_drug_class_raises(self):
        with pytest.raises((ValidationError, MedicationLeafValidationError)):
            MedicationLeaf(kind="MEDICATION", drug_class="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            MedicationLeaf(kind="MEDICATION", drug_class="NSAID",
                            unknown_field="oops")

    def test_kind_defaults_to_medication(self):
        leaf = MedicationLeaf(drug_class="PPI")
        assert leaf.kind == "MEDICATION"


class TestAllergyLeaf:
    def test_valid_leaf_parses(self):
        leaf = AllergyLeaf(kind="ALLERGY", substance_concept_id="764146007")
        assert leaf.substance_concept_id == "764146007"

    def test_valid_leaf_with_allergy_class(self):
        leaf = AllergyLeaf(kind="ALLERGY", substance_concept_id="764146007",
                            allergy_class="penicillin")
        assert leaf.allergy_class == "penicillin"

    def test_missing_substance_concept_id_raises(self):
        with pytest.raises((ValidationError, AllergyLeafValidationError)):
            AllergyLeaf(kind="ALLERGY", substance_concept_id="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            AllergyLeaf(kind="ALLERGY", substance_concept_id="764146007",
                         bad_field="x")

    def test_kind_defaults_to_allergy(self):
        leaf = AllergyLeaf(substance_concept_id="764146007")
        assert leaf.kind == "ALLERGY"


class TestTreatmentHistoryLeaf:
    def test_valid_leaf_parses(self):
        leaf = TreatmentHistoryLeaf(kind="TREATMENT_HISTORY",
                                     treatment_class="PPI")
        assert leaf.treatment_class == "PPI"
        assert leaf.min_duration_days is None

    def test_valid_leaf_with_duration(self):
        leaf = TreatmentHistoryLeaf(kind="TREATMENT_HISTORY",
                                     treatment_class="PPI",
                                     min_duration_days=28)
        assert leaf.min_duration_days == 28

    def test_missing_treatment_class_raises(self):
        with pytest.raises((ValidationError, TreatmentHistoryLeafValidationError)):
            TreatmentHistoryLeaf(kind="TREATMENT_HISTORY", treatment_class="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            TreatmentHistoryLeaf(kind="TREATMENT_HISTORY",
                                  treatment_class="PPI", nope="x")

    def test_min_duration_days_zero_raises(self):
        with pytest.raises(ValidationError):
            TreatmentHistoryLeaf(kind="TREATMENT_HISTORY",
                                  treatment_class="PPI",
                                  min_duration_days=0)

    def test_kind_defaults_to_treatment_history(self):
        leaf = TreatmentHistoryLeaf(treatment_class="H2RA")
        assert leaf.kind == "TREATMENT_HISTORY"
