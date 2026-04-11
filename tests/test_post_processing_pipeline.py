"""Integration tests for the unified post-processing pipeline.

Verifies layer ordering, input/output contracts, and the
``enable_disorder_gate`` toggle for ``run_post_processing()``.
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline.post_processing import (
    normalise_entity_types,
    link_observable_value_units,
    run_post_processing,
)
from libs.ner.post_processor_rules import PostProcessorRule

# ── Layer ordering ──


def test_layers_run_in_canonical_order() -> None:
    """Lab-value guard (L2) runs before scope guard (L3) and ConText (L7)."""
    entities = [
        {
            "text": "CKD",
            "label": "disorder",
            "start": 0,
            "end": 3,
            "assertion": "present",
        },
    ]
    encounter = "eGFR 45 mL/min CKD stage 3"

    with patch(
        "libs.pipeline.post_processing.should_suppress_disorder", return_value=True
    ):
        result = run_post_processing(encounter, entities)

    assert (
        len(result) == 0
    ), "Lab-value guard should suppress disorder before further layers"


def test_context_detection_runs_after_normalisation() -> None:
    """ConText (L7) runs on normalised entities, not raw extractions."""
    entities = [
        {
            "text": "Current smoker",
            "label": "attribute",
            "start": 0,
            "end": 14,
            "assertion": "present",
        },
    ]
    encounter = "Current smoker - 10 cigs/day"

    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing(encounter, entities)

    assert (
        result[0]["label"] == "finding"
    ), "Entity-type normalisation (L5) should run before L7"


def test_referral_procedure_possible_is_forced_to_present() -> None:
    entities = [
        {
            "text": "Fast track referral for suspected breast cancer",
            "label": "procedure",
            "start": 0,
            "end": 48,
            "assertion": "possible",
        },
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing(
            "Fast track referral for suspected breast cancer",
            entities,
        )
    assert result[0]["assertion"] == "present"
    assert result[0]["_assertion_guard"] == "referral_procedure"


# ── Input/output contracts ──


def test_run_post_processing_returns_list_of_dicts() -> None:
    entities = [
        {
            "text": "headache",
            "label": "finding",
            "start": 0,
            "end": 8,
            "assertion": "present",
        },
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing("headache noted", entities)
    assert isinstance(result, list)
    assert all(isinstance(e, dict) for e in result)


def test_run_post_processing_does_not_mutate_original() -> None:
    original = [
        {
            "text": "headache",
            "label": "finding",
            "start": 0,
            "end": 8,
            "assertion": "present",
        },
    ]
    original_copy = [dict(e) for e in original]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        run_post_processing("headache noted", original)
    assert original == original_copy, "Original entities should not be mutated"


def test_empty_entities_returns_empty() -> None:
    result = run_post_processing("some encounter text", [])
    assert result == []


# ── Post-Processor Rules (Layer 1) ──


def test_post_processor_rules_suppress_matching_entity() -> None:
    entities = [
        {
            "text": "DNA",
            "label": "finding",
            "start": 0,
            "end": 3,
            "assertion": "present",
        },
    ]
    rules = [
        PostProcessorRule(
            rule_id="r1",
            priority=1,
            action="suppress",
            match_text="DNA",
            match_label="finding",
            context_regex=None,
            window_chars=40,
            rewrite_text=None,
            rewrite_label=None,
        ),
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing("DNA received", entities, rules=rules)
    assert len(result) == 0


def test_post_processor_rules_not_applied_when_none() -> None:
    entities = [
        {
            "text": "DNA",
            "label": "finding",
            "start": 0,
            "end": 3,
            "assertion": "present",
        },
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing("DNA received", entities, rules=None)
    assert len(result) == 1


# ── Disorder gate toggle ──


def test_disorder_gate_disabled_by_default() -> None:
    entities = [
        {
            "text": "asthma",
            "label": "disorder",
            "start": 0,
            "end": 6,
            "assertion": "present",
        },
    ]
    with (
        patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"),
        patch("libs.pipeline.post_processing.verify_disorder") as mock_verify,
    ):
        result = run_post_processing("asthma diagnosed", entities)

    mock_verify.assert_not_called()
    assert len(result) == 1


def test_disorder_gate_enabled_calls_verify() -> None:
    entities = [
        {
            "text": "asthma",
            "label": "disorder",
            "start": 0,
            "end": 6,
            "assertion": "present",
        },
    ]
    with (
        patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"),
        patch("libs.pipeline.post_processing.verify_disorder") as mock_verify,
    ):
        from libs.llm_client.disorder_verifier import DisorderVerdict

        mock_verify.return_value = DisorderVerdict.ACTIVE_DIAGNOSIS
        result = run_post_processing(
            "asthma diagnosed",
            entities,
            enable_disorder_gate=True,
        )

    mock_verify.assert_called_once()
    assert len(result) == 1


def test_disorder_gate_suppresses_informational() -> None:
    entities = [
        {
            "text": "asthma",
            "label": "disorder",
            "start": 0,
            "end": 6,
            "assertion": "present",
        },
    ]
    with (
        patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"),
        patch("libs.pipeline.post_processing.verify_disorder") as mock_verify,
    ):
        from libs.llm_client.disorder_verifier import DisorderVerdict

        mock_verify.return_value = DisorderVerdict.INFORMATIONAL
        result = run_post_processing(
            "asthma discussed",
            entities,
            enable_disorder_gate=True,
        )

    assert len(result) == 0, "Informational disorders should be suppressed"


# ── Scope Guard (Layer 3) ──


def test_scope_guard_suppresses_safety_netting() -> None:
    """Safety-netting entities are REMOVED, not reclassified to hypothetical."""
    entities = [
        {
            "text": "chest pain",
            "label": "finding",
            "start": 15,
            "end": 25,
            "assertion": "present",
        },
    ]
    encounter = "If you develop chest pain, call 999"

    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing(encounter, entities)

    assert result == [], "Safety-netting entity must be suppressed (removed)"


def test_scope_guard_keeps_recommendation_as_hypothetical() -> None:
    """Conditional clinical plans stay in the pipeline as hypothetical."""
    entities = [
        {
            "text": "metformin",
            "label": "substance",
            "start": 17,
            "end": 26,
            "assertion": "present",
        },
    ]
    encounter = "Consider starting metformin if HbA1c remains elevated"

    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing(encounter, entities)

    assert len(result) == 1
    assert result[0]["assertion"] == "hypothetical"


def test_scope_guard_suppresses_instruction_indication_finding() -> None:
    entities = [
        {
            "text": "Fluoxetine 20mg capsules",
            "label": "substance",
            "start": 0,
            "end": 23,
            "assertion": "present",
        },
        {
            "text": "low mood",
            "label": "finding",
            "start": 46,
            "end": 54,
            "assertion": "present",
        },
    ]
    encounter = "Fluoxetine 20mg capsules - take two daily for low mood"

    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing(encounter, entities)

    assert any(e["text"] == "Fluoxetine 20mg capsules" for e in result)
    assert all(e["text"] != "low mood" for e in result)


def test_scope_guard_suppresses_side_effect_counselling_findings() -> None:
    encounter = (
        "pregabalin 200mg BD for radiculopathy - advised at increased risk of s/e such as "
        "dizziness, drowsiness, breathing changes, constipation, blurred vision - advised "
        "to look out for these and report back to surgery"
    )
    entities = [
        {
            "text": "dizziness",
            "label": "finding",
            "start": 83,
            "end": 92,
            "assertion": "present",
        },
        {
            "text": "drowsiness",
            "label": "finding",
            "start": 94,
            "end": 104,
            "assertion": "present",
        },
        {
            "text": "constipation",
            "label": "finding",
            "start": 124,
            "end": 136,
            "assertion": "present",
        },
        {
            "text": "blurred vision",
            "label": "finding",
            "start": 138,
            "end": 152,
            "assertion": "present",
        },
        {
            "text": "radiculopathy",
            "label": "disorder",
            "start": 32,
            "end": 44,
            "assertion": "present",
        },
    ]

    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing(encounter, entities)

    assert any(e["text"] == "radiculopathy" for e in result)
    assert all(e["text"] != "dizziness" for e in result)
    assert all(e["text"] != "drowsiness" for e in result)
    assert all(e["text"] != "constipation" for e in result)
    assert all(e["text"] != "blurred vision" for e in result)


# ── Situation Lookup (Layer 8) ──


def test_situation_lookup_adds_normalized_key() -> None:
    entities = [
        {
            "text": "referred to rheumatology",
            "label": "situation",
            "start": 0,
            "end": 24,
            "assertion": "present",
        },
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing("referred to rheumatology", entities)

    assert result[0].get("normalized_lookup") == "referral to service"


# ── Observable Normalisation (Layer 4) ──


def test_observable_span_cleaned_and_value_attached() -> None:
    entities = [
        {
            "text": "Systolic BP 145 mmHg",
            "label": "observable_entity",
            "start": 0,
            "end": 20,
            "assertion": "present",
        },
    ]
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        result = run_post_processing("Systolic BP 145 mmHg", entities)

    obs = [e for e in result if e["label"] == "observable_entity"]
    assert len(obs) >= 1
    assert obs[0].get("value") or obs[0].get(
        "unit"
    ), "Observable should have value/unit attached"
