from __future__ import annotations

from libs.ner.observable_post_processor import (
    normalize_observable_entities,
    parse_measurement_from_text,
)


def test_parse_measurement_ignores_read_code_and_extracts_true_value_unit() -> None:
    text = "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]"
    parsed = parse_measurement_from_text(text)
    assert parsed["numeric_value"] == "2.41"
    assert parsed["unit"] == "10^9/L"
    assert parsed["reference_range"] == "1.5 - 7.5"
    assert parsed["value_span"] == "2.41 10^9/L"


def test_normalize_observable_entity_splits_span_and_adds_qualifier() -> None:
    encounter = "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]"
    entities = [
        {
            "text": "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.95,
        }
    ]
    normalized = normalize_observable_entities(encounter, entities, add_qualifier_value=True)

    assert len(normalized) == 2
    obs = normalized[0]
    qv = normalized[1]

    assert obs["label"] == "observable_entity"
    assert obs["text"] == "Neutrophil count"
    assert obs["start"] == 0
    assert obs["end"] == len("Neutrophil count")
    assert obs["value"] == "2.41"
    assert obs["unit"] == "10^9/L"
    assert obs["reference_range"] == "1.5 - 7.5"

    assert qv["label"] == "qualifier_value"
    assert qv["text"] == "2.41 10^9/L"
    assert qv["start"] == encounter.index("2.41 10^9/L")
    assert qv["end"] == qv["start"] + len("2.41 10^9/L")


def test_normalize_does_not_duplicate_existing_qualifier() -> None:
    encounter = "Serum sodium level (XE2q0) 142 mmol/L [135 - 145]"
    value_text = "142 mmol/L"
    entities = [
        {
            "text": "Serum sodium level (XE2q0) 142 mmol/L [135 - 145]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.9,
        },
        {
            "text": value_text,
            "label": "qualifier_value",
            "start": encounter.index(value_text),
            "end": encounter.index(value_text) + len(value_text),
            "confidence": 0.9,
        },
    ]
    normalized = normalize_observable_entities(encounter, entities, add_qualifier_value=True)
    qualifiers = [e for e in normalized if e.get("label") == "qualifier_value" and e.get("text") == value_text]
    assert len(qualifiers) == 1


def test_parse_measurement_supports_blood_pressure_ratio_values() -> None:
    text = "BP 145/69 mmHg"
    parsed = parse_measurement_from_text(text)
    assert parsed["numeric_value"] == "145/69"
    assert parsed["unit"].lower() == "mmhg"
    assert parsed["value_span"] == "145/69 mmHg"


def test_parse_measurement_rejects_unqualified_slash_units() -> None:
    text = "value 12 / next"
    parsed = parse_measurement_from_text(text)
    assert "numeric_value" not in parsed
    assert "unit" not in parsed


def test_preserve_existing_structured_fields_by_default() -> None:
    encounter = "Neutrophil count 2.41 10^9/L [1.5 - 7.5]"
    entities = [
        {
            "text": "Neutrophil count 2.41 10^9/L [1.5 - 7.5]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "value": "9.99",
            "unit": "fake",
            "reference_range": "x-y",
        }
    ]
    normalized = normalize_observable_entities(encounter, entities)
    assert normalized[0]["value"] == "9.99"
    assert normalized[0]["unit"] == "fake"
    assert normalized[0]["reference_range"] == "x-y"
