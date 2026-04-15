from __future__ import annotations

from libs.pipeline.post_processing import (
    link_observable_value_units as _link_observable_value_units,
    normalise_entity_types as _normalise_entity_types,
)
from services.api.app.services.label_verifier import _deterministic_resolve

# ── Rule 1: Smoking status attribute/situation → finding ──


def test_smoking_status_attribute_is_normalized_to_finding() -> None:
    entities = [{"text": "Current smoker", "label": "attribute", "start": 0, "end": 14}]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "finding"


# ── Rule 2: Lab values X_DOSAGE → qualifier_value ──


def test_lab_value_x_dosage_becomes_qualifier_value() -> None:
    entities = [{"text": "142 mmol/L", "label": "X_DOSAGE", "start": 0, "end": 10}]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


# ── Rule 3: Numeric observable → qualifier_value ──


def test_numeric_observable_becomes_qualifier_value() -> None:
    entities = [
        {"text": "3.3 miu/L", "label": "observable_entity", "start": 0, "end": 9}
    ]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


# ── Rule 4: Result descriptors → qualifier_value ──


def test_result_descriptors_become_qualifier_value() -> None:
    for text in [
        "Abnormal",
        "Outside reference range",
        "NAD",
        "weight stable",
        "FOBT Non-Response",
    ]:
        entities = [{"text": text, "label": "finding", "start": 0, "end": len(text)}]
        _normalise_entity_types(entities)
        assert entities[0]["label"] == "qualifier_value", f"Failed for {text!r}"


def test_result_descriptor_from_situation_becomes_qualifier_value() -> None:
    entities = [
        {"text": "Normal - No Action", "label": "situation", "start": 0, "end": 18}
    ]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


# ── Rule 5: Episode markers → qualifier_value ──


def test_new_episode_x_temporal_becomes_qualifier_value() -> None:
    entities = [{"text": "New Episode", "label": "X_TEMPORAL", "start": 0, "end": 11}]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


def test_new_episode_x_pathway_becomes_qualifier_value() -> None:
    entities = [
        {"text": "New Episode", "label": "X_PATHWAY_MILESTONE", "start": 0, "end": 11}
    ]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


def test_ongoing_episode_becomes_qualifier_value() -> None:
    entities = [
        {"text": "Ongoing Episode", "label": "X_TEMPORAL", "start": 0, "end": 15}
    ]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


# ── Rule 6: Lifestyle factors attribute → finding ──


def test_lifestyle_factors_attribute_becomes_finding() -> None:
    for text in ["diet", "alcohol", "exercise", "weight", "drives"]:
        entities = [{"text": text, "label": "attribute", "start": 0, "end": len(text)}]
        _normalise_entity_types(entities)
        assert entities[0]["label"] == "finding", f"Failed for {text!r}"


# ── Rule 7: Smoking consumption X_DOSAGE → qualifier_value ──


def test_smoking_consumption_x_dosage_becomes_qualifier_value() -> None:
    entities = [{"text": "1-9 cigs/day", "label": "X_DOSAGE", "start": 0, "end": 12}]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


# ── Rule 8: Uncertainty markers → qualifier_value ──


def test_uncertainty_markers_become_qualifier_value() -> None:
    for text in ["??", "???", "?"]:
        entities = [{"text": text, "label": "finding", "start": 0, "end": len(text)}]
        _normalise_entity_types(entities)
        assert entities[0]["label"] == "qualifier_value", f"Failed for {text!r}"


def test_x_negation_cue_entities_are_suppressed() -> None:
    entities = [
        {"text": "No", "label": "X_NEGATION_CUE", "start": 0, "end": 2},
        {"text": "jaundice", "label": "finding", "start": 3, "end": 11},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 1
    assert entities[0]["text"] == "jaundice"


# ── Rule 9: Severity modifiers → qualifier_value ──


def test_severity_modifiers_become_qualifier_value() -> None:
    for text in ["Severe", "worsened", "pale", "Minor", "Urgent"]:
        entities = [{"text": text, "label": "attribute", "start": 0, "end": len(text)}]
        _normalise_entity_types(entities)
        assert entities[0]["label"] == "qualifier_value", f"Failed for {text!r}"


def test_severity_modifier_from_finding_becomes_qualifier_value() -> None:
    entities = [{"text": "worsened", "label": "finding", "start": 0, "end": 8}]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "qualifier_value"


# ── Rule 10: MDT → procedure; MDT outcome → record_artifact ──


def test_mdt_event_becomes_procedure() -> None:
    entities = [{"text": "MDT", "label": "event", "start": 0, "end": 3}]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "procedure"


def test_mdt_outcome_heading_becomes_record_artifact() -> None:
    entities = [
        {
            "text": "Colorectal Cancer MDT Meet Outcome",
            "label": "event",
            "start": 0,
            "end": 34,
        }
    ]
    _normalise_entity_types(entities)
    assert entities[0]["label"] == "record_artifact"


# ── Rule 11: Bare analyte near observable → suppress ──


def test_bare_analyte_substance_is_suppressed_when_observable_nearby() -> None:
    entities = [
        {
            "text": "Urine creatinine level",
            "label": "observable_entity",
            "start": 0,
            "end": 21,
        },
        {"text": "creatinine", "label": "substance", "start": 6, "end": 16},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 1
    assert entities[0]["label"] == "observable_entity"


def test_expanded_analyte_folate_suppressed() -> None:
    entities = [
        {
            "text": "Serum folate level",
            "label": "observable_entity",
            "start": 0,
            "end": 18,
        },
        {"text": "folate", "label": "substance", "start": 6, "end": 12},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 1


# ── Rule 12: Reference-range-only spans → suppress ──


def test_reference_range_only_span_is_suppressed() -> None:
    entities = [
        {"text": "Haematocrit", "label": "observable_entity", "start": 0, "end": 11},
        {"text": "[0.4 - 0.54]", "label": "observable_entity", "start": 20, "end": 32},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 1
    assert entities[0]["text"] == "Haematocrit"


# ── Rule 13: Duplicate and sub-span overlap suppression ──


def test_exact_duplicate_is_suppressed() -> None:
    entities = [
        {"text": "3.3 miu/L", "label": "qualifier_value", "start": 24, "end": 33},
        {"text": "3.3 miu/L", "label": "qualifier_value", "start": 24, "end": 33},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 1


def test_sub_span_of_same_label_is_suppressed() -> None:
    entities = [
        {
            "text": "Serum TSH level",
            "label": "observable_entity",
            "start": 0,
            "end": 15,
        },
        {"text": "Serum TSH", "label": "observable_entity", "start": 0, "end": 9},
        {"text": "TSH level", "label": "observable_entity", "start": 6, "end": 15},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 1
    assert entities[0]["text"] == "Serum TSH level"


def test_sub_span_of_different_label_is_not_suppressed() -> None:
    entities = [
        {"text": "Rheumatoid arthritis", "label": "disorder", "start": 0, "end": 20},
        {"text": "arthritis", "label": "finding", "start": 11, "end": 20},
    ]
    _normalise_entity_types(entities)
    assert len(entities) == 2


# ── Value/unit linking ──


def test_observable_gets_value_unit_from_nearby_measurement() -> None:
    entities = [
        {
            "text": "eGFR using creatinine",
            "label": "observable_entity",
            "start": 0,
            "end": 20,
        },
        {"text": "43 mL/min", "label": "qualifier_value", "start": 21, "end": 30},
    ]
    _link_observable_value_units(entities)
    assert entities[0]["value"] == "43"
    assert entities[0]["unit"] == "mL/min"


def test_observable_gets_string_value_from_nearby_qualifier() -> None:
    """VT-111-TC-001: string result after observable entity is linked."""
    entities = [
        {
            "text": "Urine culture",
            "label": "observable_entity",
            "start": 0,
            "end": 13,
        },
        {"text": "negative", "label": "qualifier_value", "start": 16, "end": 24},
    ]
    _link_observable_value_units(entities)
    assert entities[0]["value"] == "negative"
    assert entities[0]["unit"] == ""


def test_observable_gets_string_value_before_entity() -> None:
    """VT-111-TC-002: string result before observable entity is linked."""
    entities = [
        {"text": "positive", "label": "qualifier_value", "start": 0, "end": 8},
        {
            "text": "COVID antigen",
            "label": "observable_entity",
            "start": 11,
            "end": 24,
        },
    ]
    _link_observable_value_units(entities)
    obs = entities[1]
    assert obs["value"] == "positive"
    assert obs["unit"] == ""


def test_raw_text_scan_attaches_numeric_value_before_observable() -> None:
    """VT-111-TC-003: numeric value before entity captured via raw-text fallback."""
    encounter = "7.2 mmol/L HbA1c"
    entities = [
        {
            "text": "HbA1c",
            "label": "observable_entity",
            "start": 11,
            "end": 16,
        }
    ]
    _link_observable_value_units(entities, encounter)
    assert entities[0]["value"] == "7.2"
    assert entities[0]["unit"] == "mmol/L"


def test_raw_text_scan_attaches_string_value_before_observable() -> None:
    """VT-111-TC-004: string result before entity captured via raw-text fallback."""
    encounter = "negative -- Urine culture"
    entities = [
        {
            "text": "Urine culture",
            "label": "observable_entity",
            "start": 12,
            "end": 25,
        }
    ]
    _link_observable_value_units(entities, encounter)
    assert entities[0]["value"] == "negative"
    assert entities[0]["unit"] == ""


# ── Deterministic pre-resolution ──


def test_deterministic_resolves_bare_numeric_to_qualifier() -> None:
    entities = [{"text": "0.345", "label": "observable_entity", "start": 0, "end": 5}]
    result = _deterministic_resolve(
        "0.345", {"observable_entity", "qualifier_value"}, entities, 0
    )
    assert result is not None
    assert result["resolved_label"] == "qualifier_value"


def test_deterministic_resolves_numeric_measurement_to_qualifier() -> None:
    entities = [{"text": "44 iu/L", "label": "observable_entity", "start": 0, "end": 7}]
    result = _deterministic_resolve(
        "44 iu/L", {"observable_entity", "qualifier_value"}, entities, 0
    )
    assert result is not None
    assert result["resolved_label"] == "qualifier_value"


def test_deterministic_resolves_analyte_to_suppress() -> None:
    entities = [
        {
            "text": "Plasma chloride level",
            "label": "observable_entity",
            "start": 0,
            "end": 20,
        },
        {"text": "chloride", "label": "substance", "start": 7, "end": 15},
    ]
    result = _deterministic_resolve(
        "chloride", {"substance", "observable_entity"}, entities, 1
    )
    assert result is not None
    assert result["resolved_label"] == "__suppress__"


def test_deterministic_resolves_mdt_to_procedure() -> None:
    entities = [{"text": "MDT", "label": "event", "start": 0, "end": 3}]
    result = _deterministic_resolve("MDT", {"event", "procedure"}, entities, 0)
    assert result is not None
    assert result["resolved_label"] == "procedure"


def test_deterministic_returns_none_for_ambiguous() -> None:
    entities = [{"text": "screening", "label": "procedure", "start": 0, "end": 9}]
    result = _deterministic_resolve(
        "screening", {"procedure", "situation"}, entities, 0
    )
    assert result is None


def test_deterministic_resolves_episode_marker() -> None:
    entities = [{"text": "New Episode", "label": "X_TEMPORAL", "start": 0, "end": 11}]
    result = _deterministic_resolve(
        "New Episode", {"X_TEMPORAL", "qualifier_value"}, entities, 0
    )
    assert result is not None
    assert result["resolved_label"] == "qualifier_value"


def test_deterministic_resolves_x_negation_cue_misuse_prefers_azure() -> None:
    entities = [
        {"text": "Serum sodium", "label": "observable_entity", "start": 0, "end": 12}
    ]
    result = _deterministic_resolve(
        "Serum sodium",
        {"X_NEGATION_CUE", "observable_entity"},
        entities,
        0,
        model_a_label="X_NEGATION_CUE",
        model_b_label="observable_entity",
    )
    assert result is not None
    assert result["resolved_label"] == "observable_entity"
    assert "misuse" in result["reason"]


def test_deterministic_resolves_x_negation_cue_misuse_prefers_aws_when_azure_wrong() -> (
    None
):
    entities = [{"text": "creatinine", "label": "substance", "start": 0, "end": 10}]
    result = _deterministic_resolve(
        "creatinine",
        {"substance", "X_NEGATION_CUE"},
        entities,
        0,
        model_a_label="substance",
        model_b_label="X_NEGATION_CUE",
    )
    assert result is not None
    assert result["resolved_label"] == "substance"


def test_deterministic_does_not_prefer_x_negation_cue_for_real_negation_word() -> None:
    entities = [{"text": "no", "label": "finding", "start": 0, "end": 2}]
    result = _deterministic_resolve(
        "no",
        {"X_NEGATION_CUE", "finding"},
        entities,
        0,
        model_a_label="X_NEGATION_CUE",
        model_b_label="finding",
    )
    assert result is None
