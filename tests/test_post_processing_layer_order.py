"""Post-processing layer order and prompt alignment guards.

Verifies value-unit linking runs before entity-type normalisation and that
structured observables from lab panels are not demoted to qualifier_value.
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline.post_processing import (
    link_observable_value_units,
    normalise_entity_types,
    run_post_processing_with_trace,
)


def test_vt2a7c5322_value_unit_linking_runs_before_entity_type_normalisation_in_trace() -> (
    None
):
    entities = [
        {
            "text": "Hb",
            "label": "observable_entity",
            "start": 0,
            "end": 2,
            "assertion": "present",
        },
        {
            "text": "120 g/L",
            "label": "qualifier_value",
            "start": 10,
            "end": 17,
            "assertion": "present",
        },
    ]
    encounter = "Hb was 120 g/L on recent testing."

    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        _processed, trace = run_post_processing_with_trace(
            encounter, entities, enable_disorder_gate=False
        )

    completed = [row for row in trace if row.get("status") == "completed"]
    by_id = {row["layer_id"]: row for row in completed}
    assert completed.index(by_id["layer_5"]) < completed.index(by_id["layer_6"])
    assert by_id["layer_5"]["name"] == "Value-Unit Linking"
    assert by_id["layer_6"]["name"] == "Entity-Type Normalisation"
    assert completed.index(by_id["layer_4c"]) < completed.index(by_id["layer_5"])
    assert by_id["layer_4c"]["name"] == "Measurement Observable Recovery"


def test_referral_routing_guard_runs_after_lab_value_before_scope() -> None:
    entities = [
        {
            "text": "2WW referral submitted",
            "label": "procedure",
            "start": 0,
            "end": 22,
            "assertion": "present",
        },
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        _processed, trace = run_post_processing_with_trace(
            "Plan: 2WW referral submitted today.", entities, enable_disorder_gate=False
        )
    completed = [row for row in trace if row.get("status") == "completed"]
    by_id = {row["layer_id"]: row for row in completed}
    assert completed.index(by_id["layer_2"]) < completed.index(by_id["layer_2b"])
    assert completed.index(by_id["layer_2b"]) < completed.index(by_id["layer_3"])
    assert by_id["layer_2b"]["name"] == "Referral Routing Guard"
    assert _processed == []


def test_structured_observable_not_demoted_to_qualifier_value() -> None:
    entities = [
        {
            "text": "Ferritin",
            "label": "observable_entity",
            "start": 0,
            "end": 8,
            "value": "419.0",
            "unit": "ug/L",
            "assertion": "present",
        }
    ]
    normalise_entity_types(entities)
    assert entities[0]["label"] == "observable_entity"


def test_linking_fills_observable_before_entity_type_pass() -> None:
    entities = [
        {
            "text": "HbA1c",
            "label": "observable_entity",
            "start": 0,
            "end": 5,
            "assertion": "present",
        },
        {
            "text": "45.0 mmol/mol",
            "label": "qualifier_value",
            "start": 20,
            "end": 33,
            "assertion": "present",
        },
    ]
    encounter = "Endocrine panel: HbA1c result was 45.0 mmol/mol."
    link_observable_value_units(entities, encounter)
    normalise_entity_types(entities)
    obs = [e for e in entities if e["label"] == "observable_entity"]
    assert len(obs) == 1
    assert obs[0]["text"] == "HbA1c"
    assert obs[0].get("value") == "45.0"
    assert obs[0].get("unit") == "mmol/mol"
