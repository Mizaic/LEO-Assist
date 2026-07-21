"""Scaffold equity SET and observation narrative tests.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.validation_lab.models import ObservationTrigger, ValidationCaseSpec
from libs.validation_lab.scaffold import (
    materialise_case,
    render_observations_narrative,
    render_pmh_narrative,
)


def test_render_observations_narrative() -> None:
    text = render_observations_narrative(
        [ObservationTrigger(observable_id="100", value=412.0, unit="u/mL")]
    )
    assert "412" in text
    assert "u/mL" in text


def test_materialise_without_equity_does_not_set_equity_props(monkeypatch) -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "lab-plain:patient",
            "practice_id": "lab-plain:practice",
            "episode_id": "lab-plain:episode-primary",
        }
    ]
    monkeypatch.setattr(
        "libs.validation_lab.scaffold.scaffold_referral",
        lambda *a, **k: ["chunk-1"],
    )
    spec = ValidationCaseSpec(case_id="plain", title="t", referral_text="body")
    materialise_case(client, spec)
    for call in client.run.call_args_list:
        cypher = call.args[0] if call.args else ""
        assert "ethnicityConceptId" not in cypher
        assert "performanceStatusGrade" not in cypher


def test_materialise_referral_applies_care_ready_overlay(monkeypatch) -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "lab-care:patient",
            "practice_id": "lab-care:practice",
            "episode_id": "lab-care:episode-primary",
        }
    ]
    monkeypatch.setattr(
        "libs.validation_lab.scaffold.scaffold_referral",
        lambda *a, **k: ["chunk-1"],
    )
    spec = ValidationCaseSpec(
        case_id="care",
        title="Care ready",
        patient_name="Jane Doe",
        referral_text="Dear Colleague, I refer [Patient Name].\n\nJaundice.",
        gp_practice_name="Riverside Surgery",
        patient_age=48,
    )
    graph = materialise_case(client, spec)
    assert graph["gp_encounter_id"] == "lab-care:gp-consultation"
    assert graph["practice_id"] == "lab-care:practice"
    assert "Jane Doe" in graph["submission_text"]
    assert "[Patient Name]" not in graph["submission_text"]
    cypher_blob = " ".join(
        (c.args[0] if c.args else "") for c in client.run.call_args_list
    )
    assert "HAS_GENERAL_PRACTITIONER" in cypher_blob
    assert "consultation_type" in cypher_blob


def test_materialise_with_equity_sets_patient_props(monkeypatch) -> None:
    client = MagicMock()
    client.run.return_value = [
        {
            "patient_id": "lab-eq:patient",
            "practice_id": "lab-eq:practice",
            "episode_id": "lab-eq:episode-primary",
        }
    ]
    monkeypatch.setattr(
        "libs.validation_lab.scaffold.scaffold_referral",
        lambda *a, **k: ["chunk-1"],
    )
    spec = ValidationCaseSpec(
        case_id="eq",
        title="t",
        referral_text="body",
        ethnicity_concept_id="976631000000101",
        ethnicity_term="White British",
        performance_status_grade=1,
        comorbidity_band="moderate",
        core20_decile=2,
        plus_group="none",
        observations=[ObservationTrigger(observable_id="100", value=50.0, unit="U/mL")],
    )
    graph = materialise_case(client, spec)
    assert "50" in graph["submission_text"] or "50.0" in graph["submission_text"]
    equity_calls = [
        c
        for c in client.run.call_args_list
        if "ethnicityConceptId" in (c.args[0] if c.args else "")
    ]
    assert equity_calls
    params = equity_calls[0].kwargs
    assert params["ethnicity_concept_id"] == "976631000000101"
    assert params["performance_status_grade"] == 1


def test_pmh_narrative_unchanged_without_observations() -> None:
    from libs.validation_lab.models import PmhItem

    text = render_pmh_narrative(
        [PmhItem(category="condition", concept_id="1", term="Asthma")]
    )
    assert "Asthma" in text
