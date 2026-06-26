"""Unit tests for GuidelinePatientFactBundle.

Atlas trace: VT-159B4527
"""

from datetime import date

import pytest

from libs.guidelines.patient_fact_bundle import (
    AllergyFact,
    GuidelinePatientFactBundle,
    MedicationFact,
    TreatmentFact,
    empty_bundle,
)


def test_empty_bundle_does_not_raise():
    b = empty_bundle()
    assert b.active_medications == []
    assert b.allergies == []
    assert b.treatment_history == []
    assert b.patient_codes == []
    assert b.patient_observations == []
    assert b.as_of_date is None


def test_bundle_holds_one_of_each():
    med = MedicationFact(drug_class="NSAID", status="active", term="naproxen",
                         source_ids=["enc-001"])
    allergy = AllergyFact(substance_concept_id="764146007", status="active",
                          term="penicillin", source_ids=["enc-002"])
    treatment = TreatmentFact(treatment_class="PPI", outcome="failed",
                              duration_days=28, source_ids=["enc-003"])

    b = GuidelinePatientFactBundle(
        active_medications=[med],
        allergies=[allergy],
        treatment_history=[treatment],
    )

    assert len(b.active_medications) == 1
    assert b.active_medications[0].drug_class == "NSAID"
    assert b.active_medications[0].status == "active"
    assert len(b.allergies) == 1
    assert b.allergies[0].substance_concept_id == "764146007"
    assert b.allergies[0].status == "active"
    assert len(b.treatment_history) == 1
    assert b.treatment_history[0].outcome == "failed"


def test_unknown_medication_stored_without_error():
    med = MedicationFact(drug_class="NSAID", status="unknown")
    b = GuidelinePatientFactBundle(active_medications=[med])
    assert b.active_medications[0].status == "unknown"


def test_unknown_allergy_stored_without_error():
    allergy = AllergyFact(substance_concept_id="764146007", status="unknown")
    b = GuidelinePatientFactBundle(allergies=[allergy])
    assert b.allergies[0].status == "unknown"


def test_unknown_treatment_stored_without_error():
    treatment = TreatmentFact(treatment_class="PPI", outcome="unknown")
    b = GuidelinePatientFactBundle(treatment_history=[treatment])
    assert b.treatment_history[0].outcome == "unknown"


def test_as_of_date_stored_unchanged():
    d = date(2026, 1, 15)
    b = GuidelinePatientFactBundle(as_of_date=d)
    assert b.as_of_date == d


def test_source_ids_are_stored():
    med = MedicationFact(drug_class="NSAID", status="active",
                         source_ids=["enc-001", "chunk-abc"])
    b = GuidelinePatientFactBundle(active_medications=[med])
    assert b.active_medications[0].source_ids == ["enc-001", "chunk-abc"]


def test_bundle_importable_from_libs_guidelines():
    from libs.guidelines import GuidelinePatientFactBundle as B  # noqa: F401
    assert B is not None
