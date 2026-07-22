"""Regression tests for Validation Lab patient_age -> compliance path."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.validation_lab.models import ValidationCaseSpec
from libs.validation_lab.patient_age import (
    extract_age_from_text,
    resolve_patient_age,
)
from libs.validation_lab.scaffold import materialise_case
from libs.workflow.step_state_loader import (
    age_years_from_str,
    enrich_patient_demographics,
)


def test_extract_age_from_referral_prose() -> None:
    assert extract_age_from_text("62-year-old with dysphagia") == 62.0
    assert extract_age_from_text("67yo woman with cough") == 67.0
    assert extract_age_from_text("Referral for age 54 male") == 54.0


def test_resolve_patient_age_prefers_explicit_value() -> None:
    assert (
        resolve_patient_age(
            patient_age=48.0,
            case_id="abc",
            referral_text="62-year-old",
        )
        == 48.0
    )


def test_resolve_patient_age_from_referral_when_missing() -> None:
    assert (
        resolve_patient_age(
            patient_age=None,
            case_id="abc",
            referral_text="62-year-old with weight loss",
        )
        == 62.0
    )


def test_materialise_case_sets_birth_date_without_explicit_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "lab-g5:patient",
            "practice_id": "lab-g5:practice",
            "episode_id": "lab-g5:episode-primary",
        }
    ]
    captured: dict[str, float | None] = {}

    def _fake_scaffold(*_args, **kwargs):
        captured["patient_age"] = kwargs.get("patient_age")
        return ["chunk-1"]

    monkeypatch.setattr(
        "libs.validation_lab.scaffold.scaffold_referral",
        _fake_scaffold,
    )
    spec = ValidationCaseSpec(
        case_id="g5",
        title="G5.9 durable",
        referral_text="62-year-old with progressive dysphagia.",
    )
    materialise_case(client, spec)
    assert captured["patient_age"] == 62.0


def test_age_years_from_str_handles_neo4j_date_like_values() -> None:
    class _FakeDate:
        def iso_format(self) -> str:
            return "1962-06-06"

    assert age_years_from_str(_FakeDate()) is not None
    assert age_years_from_str(_FakeDate()) >= 60


def test_enrich_patient_demographics_uses_validation_lab_fallback() -> None:
    client = MagicMock()

    def _run(query: str, **params):
        if "ValidationCase" in query:
            return [
                {
                    "case_id": "37096f7c040042489b14970aac6defc1",
                    "referral_text": (
                        "62-year-old with progressive dysphagia and weight loss."
                    ),
                    "reason_for_submission": "",
                    "gp_encounter_json": "{}",
                }
            ]
        return [
            {
                "birth_date": "",
                "gender": "unknown",
                "source": "validation-lab",
            }
        ]

    client.run.side_effect = _run
    state: dict = {}
    enrich_patient_demographics(
        client,
        "lab-37096f7c040042489b14970aac6defc1:patient",
        state,
    )
    assert state.get("patient_age") == 62.0


def test_enrich_patient_demographics_reads_patient_birth_date() -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "birth_date": "1962-06-06",
            "gender": "male",
            "source": "validation-lab",
        }
    ]
    state: dict = {}
    enrich_patient_demographics(client, "lab-case:patient", state)
    assert state.get("patient_age") is not None
    assert state["patient_age"] >= 60
    assert state.get("patient_sex") == "male"
