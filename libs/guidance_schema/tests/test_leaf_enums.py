"""Unit tests for the leaf status enums.

Atlas trace: VT-159B4527 (fact bundle tests), VT-B60E3046 (evaluator tests)
"""

from libs.guidance_schema.leaf_enums import (
    AllergyStatus,
    MedicationStatus,
    TreatmentOutcome,
)


class TestMedicationStatus:
    def test_active_is_the_only_matching_value(self):
        matching = [s for s in MedicationStatus if s == MedicationStatus.active]
        assert matching == [MedicationStatus.active]

    def test_stopped_is_not_active(self):
        assert MedicationStatus.stopped != MedicationStatus.active

    def test_unknown_is_not_active(self):
        assert MedicationStatus.unknown != MedicationStatus.active

    def test_all_values_are_strings(self):
        for s in MedicationStatus:
            assert isinstance(s.value, str)

    def test_enum_accepts_string_value(self):
        assert MedicationStatus("active") == MedicationStatus.active
        assert MedicationStatus("stopped") == MedicationStatus.stopped
        assert MedicationStatus("unknown") == MedicationStatus.unknown


class TestAllergyStatus:
    def test_active_is_only_matching_value(self):
        matching = [s for s in AllergyStatus if s == AllergyStatus.active]
        assert matching == [AllergyStatus.active]

    def test_nkda_and_unknown_are_distinct(self):
        assert AllergyStatus.nkda != AllergyStatus.unknown

    def test_nkda_is_not_active(self):
        assert AllergyStatus.nkda != AllergyStatus.active

    def test_unknown_is_not_active(self):
        assert AllergyStatus.unknown != AllergyStatus.active

    def test_enum_accepts_string_value(self):
        assert AllergyStatus("nkda") == AllergyStatus.nkda
        assert AllergyStatus("unknown") == AllergyStatus.unknown


class TestTreatmentOutcome:
    def test_failed_and_not_tolerated_are_matches(self):
        matches = {TreatmentOutcome.failed, TreatmentOutcome.not_tolerated}
        non_matches = {
            TreatmentOutcome.completed,
            TreatmentOutcome.ongoing,
            TreatmentOutcome.planned,
            TreatmentOutcome.unknown,
        }
        assert matches.isdisjoint(non_matches)

    def test_planned_is_not_a_match(self):
        assert TreatmentOutcome.planned != TreatmentOutcome.failed
        assert TreatmentOutcome.planned != TreatmentOutcome.not_tolerated

    def test_unknown_is_not_a_match(self):
        assert TreatmentOutcome.unknown != TreatmentOutcome.failed

    def test_enum_accepts_string_value(self):
        assert TreatmentOutcome("failed") == TreatmentOutcome.failed
        assert TreatmentOutcome("not_tolerated") == TreatmentOutcome.not_tolerated
