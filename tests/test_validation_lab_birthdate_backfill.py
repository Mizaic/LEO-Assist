"""Unit tests for Validation Lab birthDate backfill."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.validation_lab.birthdate_backfill import (
    backfill_validation_lab_birthdates,
    case_id_from_patient_id,
    count_missing_birthdate_patients,
    plan_backfill_rows,
    resolve_birth_date_for_row,
)


def test_case_id_from_patient_id() -> None:
    assert (
        case_id_from_patient_id("lab-37096f7c040042489b14970aac6defc1:patient")
        == "37096f7c040042489b14970aac6defc1"
    )
    assert case_id_from_patient_id("not-a-lab-patient") == ""


def test_resolve_birth_date_from_referral_text() -> None:
    birth_date = resolve_birth_date_for_row(
        {
            "patient_id": "lab-37096f7c040042489b14970aac6defc1:patient",
            "case_id": "37096f7c040042489b14970aac6defc1",
            "referral_text": (
                "62-year-old with progressive dysphagia and weight loss."
            ),
            "reason_for_submission": "",
            "gp_encounter_json": "",
        }
    )
    assert birth_date.endswith("-07-22") or birth_date.count("-") == 2
    assert int(birth_date[:4]) <= 2004


def test_plan_backfill_rows_skips_empty_patient_id() -> None:
    planned = plan_backfill_rows(
        [
            {
                "patient_id": "",
                "case_id": "abc",
                "referral_text": "62-year-old",
            },
            {
                "patient_id": "lab-abc:patient",
                "case_id": "abc",
                "referral_text": "62-year-old with cough",
            },
        ]
    )
    assert len(planned) == 1
    assert planned[0]["patient_id"] == "lab-abc:patient"
    assert planned[0]["birth_date"]


def test_backfill_dry_run_does_not_write() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"missing_count": 2}],
        [
            {
                "patient_id": "lab-case:patient",
                "case_id": "case",
                "referral_text": "62-year-old",
                "reason_for_submission": "",
                "gp_encounter_json": "",
            }
        ],
    ]
    report = backfill_validation_lab_birthdates(client, dry_run=True)
    assert report.missing_before == 2
    assert report.planned == 1
    assert report.updated == 0
    assert report.missing_after == 2
    assert report.updates[0]["birth_date"]
    assert client.run.call_count == 2


def test_backfill_apply_writes_and_recounts() -> None:
    client = MagicMock()
    client.run.side_effect = [
        [{"missing_count": 1}],
        [
            {
                "patient_id": "lab-case:patient",
                "case_id": "case",
                "referral_text": "62-year-old",
                "reason_for_submission": "",
                "gp_encounter_json": "",
            }
        ],
        [{"patient_id": "lab-case:patient", "birth_date": "1964-07-22"}],
        [{"missing_count": 0}],
    ]
    report = backfill_validation_lab_birthdates(client, dry_run=False)
    assert report.planned == 1
    assert report.updated == 1
    assert report.missing_after == 0
    assert client.run.call_count == 4


def test_count_missing_birthdate_patients_defaults_to_zero() -> None:
    client = MagicMock()
    client.run.return_value = []
    assert count_missing_birthdate_patients(client) == 0
