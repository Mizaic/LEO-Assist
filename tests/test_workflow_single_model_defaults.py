"""Validation workflows pin to a single Haiku LLM path."""

from __future__ import annotations

from libs.workflow.model_defaults import apply_single_model_defaults


def test_validation_run_defaults_to_llm_small():
    state: dict = {"capture_validation_output": True}
    apply_single_model_defaults(state)
    assert state["requested_model_mode"] == "llm"
    assert state["model_mode"] == "llm"
    assert state["model_tier"] == "small"


def test_production_run_untouched():
    state: dict = {"patient_id": "p1"}
    apply_single_model_defaults(state)
    assert "requested_model_mode" not in state
    assert "model_tier" not in state


def test_explicit_model_mode_not_overwritten():
    state: dict = {
        "validation_un_id": "UN-89E2AE36",
        "model_mode": "ner",
    }
    apply_single_model_defaults(state)
    assert state["model_mode"] == "ner"
    assert state["model_tier"] == "small"
