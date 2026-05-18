"""Unit tests for deterministic NCDA diagnosis-route classification."""

from __future__ import annotations

from services.analysis_worker.app.ncda_detector.route_classifier import (
    classify_diagnosis_route,
)
from services.analysis_worker.app.ncda_detector.simple_linker import (
    EncounterRow,
    SimplePathway,
)


def _labeled(rows: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return sorted(rows, key=lambda x: x[0])


def test_cohort_1a_gp_fast_track_default() -> None:
    ftr = EncounterRow(
        encounter_id="e1",
        encounter_date="2025-01-01",
        role="ftr",
        outcome=None,
        text="Fast track referral for suspected lung cancer (XaMeC)",
        site=None,
    )
    dx = EncounterRow(
        encounter_id="e2",
        encounter_date="2025-02-01",
        role="dx",
        outcome="cancer_found",
        text="MDT outcome malignant",
        site=None,
    )
    pw = SimplePathway(
        patient_id="p",
        cohort="1a",
        ftr=ftr,
        dx=dx,
    )
    lab = _labeled(
        [
            ("2025-01-01", ftr.text or "", "ftr"),
            ("2025-02-01", dx.text or "", "dx"),
        ]
    )
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "gp_surgery_fast_track"


def test_cohort_1a_screening_read_code_on_ftr() -> None:
    ftr = EncounterRow(
        encounter_id="e1",
        encounter_date="2025-01-01",
        role="ftr",
        outcome=None,
        text="Referral letter (68621) NHS Breast Screening abnormal",
        site=None,
    )
    dx = EncounterRow(
        encounter_id="e2",
        encounter_date="2025-02-01",
        role="dx",
        outcome="cancer_found",
        text="Invasive ductal carcinoma",
        site=None,
    )
    pw = SimplePathway(patient_id="p", cohort="1a", ftr=ftr, dx=dx)
    lab = _labeled(
        [
            ("2025-01-01", ftr.text or "", "ftr"),
            ("2025-02-01", dx.text or "", "dx"),
        ]
    )
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "screening"


def test_cohort_3_emergency_before_dx() -> None:
    dx = EncounterRow(
        encounter_id="e2",
        encounter_date="2025-03-01",
        role="dx",
        outcome="cancer_found",
        text="Malignant obstruction — inpatient diagnosis",
        site=None,
    )
    pw = SimplePathway(patient_id="p", cohort="3", dx=dx)
    lab = _labeled(
        [
            ("2025-02-01", "Patient attended A&E with obstructive symptoms", "none"),
            ("2025-03-01", dx.text or "", "dx"),
        ]
    )
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "emergency_or_urgent_care"


def test_linked_ftr_takes_precedence_over_old_emergency_text() -> None:
    ftr = EncounterRow(
        encounter_id="e2",
        encounter_date="2025-02-01",
        role="ftr",
        outcome=None,
        text="Fast track referral for suspected breast cancer",
        site=None,
    )
    dx = EncounterRow(
        encounter_id="e3",
        encounter_date="2025-03-01",
        role="dx",
        outcome="cancer_found",
        text="Invasive breast carcinoma",
        site=None,
    )
    pw = SimplePathway(patient_id="p", cohort="1a", ftr=ftr, dx=dx)
    lab = _labeled(
        [
            ("2025-01-01", "Patient attended A&E with unrelated fall", "none"),
            ("2025-02-01", ftr.text or "", "ftr"),
            ("2025-03-01", dx.text or "", "dx"),
        ]
    )
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "gp_surgery_fast_track"


def test_cohort_2_unknown() -> None:
    ftr = EncounterRow(
        encounter_id="e1",
        encounter_date="2025-01-01",
        role="ftr",
        outcome=None,
        text="Fast track referral",
        site=None,
    )
    pw = SimplePathway(patient_id="p", cohort="2", ftr=ftr)
    lab = _labeled([("2025-01-01", ftr.text or "", "ftr")])
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "unknown"


def test_cohort_3_old_emergency_text_does_not_classify_as_emergency() -> None:
    """Emergency text more than 90 days before Dx is not the diagnosis route."""
    dx = EncounterRow(
        encounter_id="e2",
        encounter_date="2025-06-01",
        role="dx",
        outcome="cancer_found",
        text="Malignant neoplasm - secondary care diagnosis letter",
        site=None,
    )
    pw = SimplePathway(patient_id="p", cohort="3", dx=dx)
    lab = _labeled(
        [
            ("2024-01-15", "Attended A&E for chest pain - discharged", "none"),
            ("2025-06-01", dx.text or "", "dx"),
        ]
    )
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "external_or_unknown_route"


def test_cohort_3_external_or_unknown_default() -> None:
    """No GP fast track, no emergency, no screening, no surveillance text near
    the Dx. Should default to external_or_unknown_route, not emergency."""
    dx = EncounterRow(
        encounter_id="e1",
        encounter_date="2025-05-05",
        role="dx",
        outcome="cancer_found",
        text="Cancer diagnosis from secondary care",
        site=None,
    )
    pw = SimplePathway(patient_id="p", cohort="3", dx=dx)
    lab = _labeled(
        [
            ("2025-05-05", dx.text or "", "dx"),
            ("2025-05-08", "Treatment plan discussed", "treatment"),
        ]
    )
    rc = classify_diagnosis_route(pw, labeled_encounters=lab)
    assert rc.route == "external_or_unknown_route"
