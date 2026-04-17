"""Pipeline parity tests: training and runtime produce identical post-processing.

These tests verify that the same input entities processed through the
training path and the runtime path produce identical results, eliminating
train/serve skew.  The disorder gate is excluded from parity comparison
since it is an explicit, documented deviation (enabled in training,
disabled at runtime).
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline.post_processing import run_post_processing


def _strip_internal_keys(entities: list[dict]) -> list[dict]:
    """Remove internal keys that are adapter-specific (e.g. __sentence_id)."""
    return [{k: v for k, v in e.items() if not k.startswith("__")} for e in entities]


def _run_training_mode(encounter_text: str, entities: list[dict]) -> list[dict]:
    """Simulate training pipeline post-processing."""
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        return _strip_internal_keys(
            run_post_processing(
                encounter_text,
                entities,
                enable_disorder_gate=False,
                coding_mode="hitl",
            )
        )


def _run_runtime_mode(encounter_text: str, entities: list[dict]) -> list[dict]:
    """Simulate runtime pipeline post-processing."""
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        return _strip_internal_keys(
            run_post_processing(
                encounter_text,
                entities,
                enable_disorder_gate=False,
                coding_mode="hitl",
            )
        )


def _assert_parity(encounter_text: str, entities: list[dict]) -> None:
    """Assert training and runtime produce identical output."""
    training_result = _run_training_mode(encounter_text, entities)
    runtime_result = _run_runtime_mode(encounter_text, entities)
    assert (
        training_result == runtime_result
    ), f"Parity failure:\n  training={training_result}\n  runtime={runtime_result}"


# ── Parity tests ──


def test_parity_simple_finding() -> None:
    _assert_parity(
        "Patient has headache",
        [
            {
                "text": "headache",
                "label": "finding",
                "start": 12,
                "end": 20,
                "assertion": "present",
            }
        ],
    )


def test_parity_lab_value_guard() -> None:
    _assert_parity(
        "eGFR 45 mL/min suggestive of CKD",
        [
            {
                "text": "eGFR",
                "label": "observable_entity",
                "start": 0,
                "end": 4,
                "assertion": "present",
            },
            {
                "text": "45 mL/min",
                "label": "qualifier_value",
                "start": 5,
                "end": 14,
                "assertion": "present",
            },
            {
                "text": "CKD",
                "label": "disorder",
                "start": 29,
                "end": 32,
                "assertion": "present",
            },
        ],
    )


def test_parity_scope_guard_recommendation() -> None:
    _assert_parity(
        "Consider starting metformin 500mg BD",
        [
            {
                "text": "metformin",
                "label": "medicinal_product",
                "start": 18,
                "end": 27,
                "assertion": "present",
            },
        ],
    )


def test_parity_entity_type_normalisation() -> None:
    _assert_parity(
        "Smoking status: Current smoker, 10 cigs/day",
        [
            {
                "text": "Current smoker",
                "label": "attribute",
                "start": 16,
                "end": 30,
                "assertion": "present",
            },
            {
                "text": "10 cigs/day",
                "label": "X_DOSAGE",
                "start": 32,
                "end": 43,
                "assertion": "present",
            },
        ],
    )


def test_parity_suppression_rules() -> None:
    _assert_parity(
        "No jaundice",
        [
            {
                "text": "No",
                "label": "X_NEGATION_CUE",
                "start": 0,
                "end": 2,
                "assertion": "present",
            },
            {
                "text": "jaundice",
                "label": "finding",
                "start": 3,
                "end": 11,
                "assertion": "present",
            },
        ],
    )


def test_parity_observable_normalisation() -> None:
    _assert_parity(
        "Systolic BP 145 mmHg [120-180]",
        [
            {
                "text": "Systolic BP 145 mmHg [120-180]",
                "label": "observable_entity",
                "start": 0,
                "end": 30,
                "assertion": "present",
            },
        ],
    )


def test_parity_lab_triple_recovery_reticulocyte_observation() -> None:
    """Recovery layer must produce identical triples in train and runtime.

    Reproduces the production defect from the user's bug report: the
    Reticulocyte observation line where the model emits nothing and
    Layer 3b must add procedure / observable_entity / finding.
    """
    _assert_parity(
        "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] "
        "- Outside reference range",
        [],
    )


def test_parity_situation_lookup() -> None:
    _assert_parity(
        "Referred to cardiology for assessment",
        [
            {
                "text": "Referred to cardiology",
                "label": "situation",
                "start": 0,
                "end": 22,
                "assertion": "present",
            },
        ],
    )


def test_parity_empty_entities() -> None:
    _assert_parity("Some encounter text", [])


def test_parity_multiple_entities_mixed_types() -> None:
    _assert_parity(
        "BP 145/90 mmHg. Headache worsening. Current smoker.",
        [
            {
                "text": "BP 145/90 mmHg",
                "label": "observable_entity",
                "start": 0,
                "end": 14,
                "assertion": "present",
            },
            {
                "text": "Headache",
                "label": "finding",
                "start": 16,
                "end": 24,
                "assertion": "present",
            },
            {
                "text": "worsening",
                "label": "finding",
                "start": 25,
                "end": 34,
                "assertion": "present",
            },
            {
                "text": "Current smoker",
                "label": "attribute",
                "start": 36,
                "end": 50,
                "assertion": "present",
            },
        ],
    )
