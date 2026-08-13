"""VT for DI-B5C78811: retag split weight/height/BMI as observables.

Atlas trace:
  DI: DI-B5C78811
  DO: DO-728930A1
  VT: VT-E6BD0CA9
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-E6BD0CA9")

Run: pytest tests/test_measurement_observable_recovery.py -v --no-cov
"""

from __future__ import annotations

import json

from libs.ner.measurement_observable_recovery import recover_measurement_observables
from libs.pipeline.post_processing import run_post_processing
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

_VITALS = "- Height: 1.67 m\n" "- Current weight: 67 kg\n" "- BMI: 24.0 kg/m2"


def _split_entities() -> list[dict]:
    return [
        {"text": "- Current weight", "label": "procedure", "start": 18, "end": 35},
        {"text": "67 kg", "label": "qualifier_value", "start": 37, "end": 42},
        {"text": "- Height", "label": "procedure", "start": 0, "end": 8},
        {"text": "1.67 m", "label": "qualifier_value", "start": 10, "end": 16},
        {"text": "BMI", "label": "finding", "start": 45, "end": 48},
        {"text": "24.0 kg/m", "label": "qualifier_value", "start": 50, "end": 59},
    ]


def test_current_weight_becomes_observable_with_value_and_unit() -> None:
    out = recover_measurement_observables(_VITALS, _split_entities())
    weight = next(e for e in out if e["text"] == "current weight")
    assert weight["label"] == "observable_entity"
    assert weight["lookup_term"] == "current body weight"
    assert weight["value"] == "67"
    assert weight["unit"] == "kg"


def test_height_and_bmi_recover_from_the_same_list() -> None:
    out = recover_measurement_observables(_VITALS, _split_entities())
    by_name = {e["text"]: e for e in out}
    assert by_name["height"]["value"] == "1.67"
    assert by_name["height"]["unit"] == "m"
    assert by_name["bmi"]["value"] == "24.0"
    assert by_name["bmi"]["unit"] == "kg/m2"
    assert by_name["bmi"]["label"] == "observable_entity"


def test_orphan_numbers_are_not_kept() -> None:
    out = recover_measurement_observables(_VITALS, _split_entities())
    texts = {e["text"] for e in out}
    assert "67 kg" not in texts
    assert "24.0 kg/m" not in texts
    assert "1.67 m" not in texts


def test_recovers_from_source_line_when_offsets_are_missing() -> None:
    entities = [
        {"text": "- Current weight", "label": "procedure", "start": 0, "end": 0},
        {"text": "67 kg", "label": "qualifier_value", "start": 0, "end": 0},
    ]
    out = recover_measurement_observables(_VITALS, entities)
    assert len(out) == 1
    assert out[0]["text"] == "current weight"
    assert out[0]["value"] == "67"
    assert out[0]["unit"] == "kg"


def test_links_value_on_the_next_line_by_offset() -> None:
    text = "- Current weight\n67 kg"
    entities = [
        {"text": "- Current weight", "label": "procedure", "start": 0, "end": 16},
        {"text": "67 kg", "label": "qualifier_value", "start": 17, "end": 22},
    ]
    out = recover_measurement_observables(text, entities)
    assert len(out) == 1
    assert out[0]["value"] == "67"
    assert out[0]["unit"] == "kg"


def test_weighing_procedure_without_value_stays_procedure() -> None:
    entities = [
        {
            "text": "Weighing patient",
            "label": "procedure",
            "start": 0,
            "end": 16,
        }
    ]
    out = recover_measurement_observables("Weighing patient in clinic.", entities)
    assert out[0]["label"] == "procedure"
    assert out[0].get("value") is None


def test_unrelated_procedure_near_a_number_is_not_retagged() -> None:
    text = "Colonoscopy: 2 cm polyp removed."
    entities = [
        {"text": "Colonoscopy", "label": "procedure", "start": 0, "end": 11},
        {"text": "2 cm", "label": "qualifier_value", "start": 13, "end": 17},
    ]
    out = recover_measurement_observables(text, entities)
    assert out[0]["label"] == "procedure"
    assert out[1]["text"] == "2 cm"


def test_run_post_processing_attaches_weight_before_coding() -> None:
    out = run_post_processing(_VITALS, _split_entities(), enable_disorder_gate=False)
    weight = next(e for e in out if "weight" in str(e.get("text") or "").lower())
    assert weight["label"] == "observable_entity"
    assert weight["value"] == "67"
    assert weight["unit"] == "kg"


def test_extraction_prompt_tells_model_vitals_are_observables() -> None:
    assert "Current weight: 67 kg" in EXTRACTION_SYSTEM_V1
    assert "observable entity, not procedure" in EXTRACTION_SYSTEM_V1


def test_bullet_vitals_few_shot_keeps_value_on_observable() -> None:
    example = next(
        ex
        for ex in EXTRACTION_EXAMPLES
        if "Bullet vitals" in str(ex.get("description", ""))
    )
    terms = json.loads(example["output"])["terms"]
    by_text = {t["text"]: t for t in terms}
    assert by_text["Current weight"]["semantic_tag"] == "observable entity"
    assert by_text["Current weight"]["value"] == "67"
    assert by_text["Current weight"]["unit"] == "kg"
