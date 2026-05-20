"""Tests for Layer 4b: Observable Surface Cleanup.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B5C78811
  DO: DO-728930A1
  VT: VT-29880CC8

Verifies that observable_entity surface forms are stripped of trailing
value/unit/reference-range tokens by the canonical post-processing stack so
production and validation see the same canonical name.
"""

from __future__ import annotations

from libs.pipeline.post_processing import (
    clean_observable_surface_forms,
    run_post_processing,
)


def test_layer_4b_strips_value_unit_and_range_from_observable_text():
    entities = [
        {
            "text": "Haemoglobin 124 g/L (115-160)",
            "label": "observable_entity",
            "start": 0,
            "end": 30,
        }
    ]
    cleaned = clean_observable_surface_forms(entities)
    assert cleaned[0]["text"] == "Haemoglobin"
    # The raw surface form is preserved for audit when cleanup occurs.
    assert cleaned[0]["__raw_text"] == "Haemoglobin 124 g/L (115-160)"


def test_layer_4b_drops_observable_that_collapses_to_bare_number():
    entities = [
        {
            "text": "5.2 g/L",
            "label": "observable_entity",
            "start": 0,
            "end": 7,
        },
        {
            "text": "Haemoglobin",
            "label": "observable_entity",
            "start": 10,
            "end": 21,
        },
    ]
    cleaned = clean_observable_surface_forms(entities)
    texts = [ent["text"] for ent in cleaned]
    assert texts == ["Haemoglobin"]


def test_layer_4b_leaves_non_observable_entities_alone():
    entities = [
        {
            "text": "asthma 5 g/L",
            "label": "disorder",
            "start": 0,
            "end": 12,
        }
    ]
    cleaned = clean_observable_surface_forms(entities)
    assert cleaned[0]["text"] == "asthma 5 g/L"
    assert "__raw_text" not in cleaned[0]


def test_layer_4b_is_idempotent():
    entities = [
        {
            "text": "Platelet count 250 x10^9/L",
            "label": "observable_entity",
            "start": 0,
            "end": 28,
        }
    ]
    once = clean_observable_surface_forms([dict(e) for e in entities])
    twice = clean_observable_surface_forms([dict(e) for e in once])
    assert once[0]["text"] == "Platelet count"
    assert twice[0]["text"] == "Platelet count"
    # Raw text is recorded only on first pass.
    assert twice[0]["__raw_text"] == "Platelet count 250 x10^9/L"


def test_layer_4b_strips_ferritin_ug_per_l_tail() -> None:
    entities = [
        {
            "text": "Ferritin 419.0 ug/L",
            "label": "observable_entity",
            "start": 0,
            "end": 19,
            "value": "419.0",
            "unit": "ug/L",
        }
    ]
    cleaned = clean_observable_surface_forms(entities)
    assert cleaned[0]["text"] == "Ferritin"


def test_layer_4b_runs_through_full_post_processing():
    """End-to-end check that the layer is wired into run_post_processing.

    A simple observable_entity carrying a value/unit/range tail should come
    out the back of run_post_processing with the canonical name only.
    """
    encounter_text = "Patient seen. Haemoglobin 124 g/L (115-160). Stable."
    entities = [
        {
            "text": "Haemoglobin 124 g/L (115-160)",
            "label": "observable_entity",
            "start": encounter_text.find("Haemoglobin"),
            "end": encounter_text.find("Haemoglobin") + len("Haemoglobin 124 g/L (115-160)"),
            "assertion": "present",
        }
    ]
    processed = run_post_processing(encounter_text, entities)
    observables = [e for e in processed if e.get("label") == "observable_entity"]
    assert observables, "Expected at least one observable entity to survive"
    assert any(e["text"] == "Haemoglobin" for e in observables)
