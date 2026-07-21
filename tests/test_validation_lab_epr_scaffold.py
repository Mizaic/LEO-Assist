"""Tests for primary-care EPR Lab scaffold.

Atlas: DI-3002D641 / VT-B79AF7AC
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.validation_lab.epr_scaffold import (
    auto_gp_encounter_from_text,
    generate_lab_nhs_number,
    is_spoa_scenario,
    scaffold_epr_patient,
    write_gp_consultation,
)
from libs.validation_lab.models import EncounterSpec, ValidationCaseSpec


def test_is_spoa_scenario() -> None:
    assert is_spoa_scenario("spo_ag")
    assert is_spoa_scenario("ras_referral")
    assert not is_spoa_scenario("generic")


def test_generate_lab_nhs_number_is_stable() -> None:
    assert generate_lab_nhs_number("case-a") == generate_lab_nhs_number("case-a")
    assert len(generate_lab_nhs_number("case-a")) == 10


def test_scaffold_epr_patient_writes_practice_and_episode() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "lab-1:patient",
            "practice_id": "lab-1:practice",
            "episode_id": "lab-1:episode-primary",
        }
    ]
    spec = ValidationCaseSpec(
        case_id="1",
        title="SPoA patient",
        scenario_type="spo_ag",
        case_type="ag",
        patient_name="Test Patient",
        nhs_number="9990000001",
        gp_practice_name="Demo Surgery",
    )
    result = scaffold_epr_patient(client, spec, patient_id="lab-1:patient")
    assert result["nhs_number"] == "9990000001"
    assert result["practice_id"] == "lab-1:practice"
    query = client.run.call_args.args[0]
    assert "HAS_GENERAL_PRACTITIONER" in query
    assert "ep.episode_id = $episode_id" in query
    kwargs = client.run.call_args.kwargs
    assert kwargs["nhs_number"] == "9990000001"
    assert kwargs["practice_name"] == "Demo Surgery"


def test_auto_gp_encounter_from_text_builds_soap_not_letter() -> None:
    enc = auto_gp_encounter_from_text(
        "Dear Hepatology Team,\n\n"
        "Jaundice for 2 weeks.\n\n"
        "Please advise on urgent scan."
    )
    assert enc.label == "GP consultation"
    assert enc.text.startswith("Subjective:")
    assert "Dear Hepatology" not in enc.text
    assert "Jaundice" in enc.text
    assert enc.date


def test_write_gp_consultation_sets_consultation_type() -> None:
    client = MagicMock()
    write_gp_consultation(
        client,
        patient_id="p1",
        case_id="1",
        encounter=EncounterSpec(text="Cough", date="2026-01-01"),
    )
    query = client.run.call_args.args[0]
    assert "consultation_type" in query


def test_write_gp_consultation_requires_text() -> None:
    client = MagicMock()
    try:
        write_gp_consultation(
            client,
            patient_id="p1",
            case_id="1",
            encounter=EncounterSpec(text=""),
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "gp_encounter.text" in str(exc)


def test_write_gp_consultation_sets_kind() -> None:
    client = MagicMock()
    eid = write_gp_consultation(
        client,
        patient_id="p1",
        case_id="1",
        encounter=EncounterSpec(
            label="GP visit", text="Cough for 2 weeks", date="2026-01-01"
        ),
    )
    assert eid == "lab-1:gp-consultation"
    kwargs = client.run.call_args.kwargs
    assert kwargs["text"] == "Cough for 2 weeks"
    assert "gp_consultation" in client.run.call_args.args[0]
