"""End-to-end test of lab triple recovery through the full post-processing stack.

Covers VT-LEO-AI-155. Drives the whole ``run_post_processing()`` chain on
the production defect line and asserts that:

1. The procedure / observable_entity / finding triple is recovered.
2. Layer 4 (Observable Normalisation) then enriches the recovered
   observable with structured value, unit, and reference_range fields.
3. Layer 6 (Value-Unit Linking) does not need to invent anything because
   Layer 4 already populated the structured fields from the observable
   text itself.
4. The recovery is idempotent and does not duplicate any spans on a
   second pass through the pipeline.
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline.post_processing import (
    run_post_processing,
    run_post_processing_with_trace,
)


PROD_DEFECT_LINE = (
    "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80] "
    "- Outside reference range"
)


def _by_label(entities, label):
    return [e for e in entities if e.get("label") == label]


def _without_internal_keys(entities):
    return [
        {k: v for k, v in e.items() if not k.startswith("__")}
        for e in entities
    ]


def _run(text, entities):
    """Run post-processing with ConText disabled (test isolation)."""
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        return _without_internal_keys(
            run_post_processing(
                text,
                entities,
                enable_disorder_gate=False,
                coding_mode="hitl",
            )
        )


def test_full_pipeline_recovers_triple_on_production_defect_line() -> None:
    """The whole pipeline must produce procedure + observable + finding.

    Reproduces the production defect: when the NER model and the LLM
    extractor both miss the long observable span, the post-processing
    stack must still recover and enrich it.
    """
    out = _run(PROD_DEFECT_LINE, [])

    assert _by_label(out, "procedure"), "procedure not recovered"
    assert _by_label(out, "observable_entity"), "observable_entity not recovered"
    assert _by_label(out, "finding"), "finding not recovered"


def test_layer_4_enriches_recovered_observable_with_structured_fields() -> None:
    """Once recovered, the observable carries value, unit, and reference_range."""
    out = _run(PROD_DEFECT_LINE, [])
    observables = _by_label(out, "observable_entity")
    assert observables
    obs = observables[0]
    assert obs.get("value") == "96"
    assert "10^9" in str(obs.get("unit", ""))
    assert "L" in str(obs.get("unit", ""))
    assert "20" in str(obs.get("reference_range", ""))
    assert "80" in str(obs.get("reference_range", ""))


def test_recovery_is_idempotent_through_full_pipeline() -> None:
    """Running the pipeline twice on the same input must not duplicate spans."""
    once = _run(PROD_DEFECT_LINE, [])
    once_input = [dict(e) for e in once]
    twice = _run(PROD_DEFECT_LINE, once_input)

    once_keys = sorted(
        (e.get("label"), e.get("start"), e.get("end")) for e in once
    )
    twice_keys = sorted(
        (e.get("label"), e.get("start"), e.get("end")) for e in twice
    )
    assert once_keys == twice_keys


def test_recovery_skipped_when_procedure_and_observable_already_present() -> None:
    """Existing model output is preserved; only missing finding is added."""
    seed = [
        {
            "text": "Reticulocyte count - observation",
            "label": "procedure",
            "start": 0,
            "end": 32,
            "assertion": "present",
        },
        {
            "text": "Reticulocyte count - observation (42X..) 96 10^9/L [20 - 80]",
            "label": "observable_entity",
            "start": 0,
            "end": 60,
            "assertion": "present",
        },
    ]
    out = _run(PROD_DEFECT_LINE, seed)

    procedures = _by_label(out, "procedure")
    observables = _by_label(out, "observable_entity")
    assert len(procedures) == 1
    assert len(observables) >= 1


def test_layer_3b_appears_in_trace_with_three_added_entities() -> None:
    """The trace must show layer_3b adding the recovered triple."""
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        _entities, trace = run_post_processing_with_trace(
            PROD_DEFECT_LINE,
            [],
            enable_disorder_gate=False,
        )

    layer_3b_entries = [t for t in trace if t.get("layer_id") == "layer_3b"]
    assert len(layer_3b_entries) == 1
    layer = layer_3b_entries[0]
    assert layer["status"] == "completed"
    assert layer["added_count"] == 3


def test_full_pipeline_handles_multi_line_lab_block() -> None:
    """Every lab line in a block must be recovered and enriched."""
    text = (
        "Full Blood Count results:\n"
        "Reticulocyte count (42X..) 96 10^9/L [20 - 80] - Outside reference range\n"
        "Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range\n"
    )
    out = _run(text, [])
    procedure_texts = {e["text"] for e in _by_label(out, "procedure")}
    assert "Reticulocyte count" in procedure_texts
    assert "Mean cell volume" in procedure_texts

    findings = _by_label(out, "finding")
    assert len(findings) >= 2
