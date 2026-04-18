"""Unit VT for the classifier agent (VT-LEO-AI-502)."""

from __future__ import annotations

import pytest

from services.analysis_worker.app.episode_engine.agents import classifier
from services.analysis_worker.app.episode_engine.agents._common import StageError
from services.analysis_worker.app.episode_engine.schemas import ClassifierResult
from tests.episode_engine.conftest import (
    FakeLLM,
    FakeLLMResponse,
    tool_use,
)


def _run(llm: FakeLLM, **overrides):
    kwargs = dict(
        llm=llm,
        patient_id="p-1",
        window_id="w1",
        suspected_site="breast",
        window_start="2025-03-26",
        window_end="2025-07-28",
        window_text="2WW referral followed by clinic and surgery.",
    )
    kwargs.update(overrides)
    return classifier.run(**kwargs)


def test_classifier_parses_cancer_verdict():
    """VT-502-TC-001: structured cancer verdict survives the round-trip."""

    payload = {
        "window_id": "w1",
        "episode_type": "cancer",
        "confidence": 0.93,
        "reasoning": "Confirmed breast cancer pathway.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_classification", payload)]))

    result, trace = _run(llm)
    assert isinstance(result, ClassifierResult)
    assert result.episode_type == "cancer"
    assert result.confidence == pytest.approx(0.93)
    assert result.window_id == "w1"
    assert trace.stage == "classifier"
    assert trace.ok is True


def test_classifier_handles_open_ended_window():
    """VT-502-TC-002: window_end may be None and the user prompt copes."""

    payload = {
        "window_id": "w1",
        "episode_type": "uncertain",
        "confidence": 0.5,
        "reasoning": "Not enough evidence yet.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_classification", payload)]))

    result, _ = _run(llm, window_end=None)
    assert result.episode_type == "uncertain"
    assert llm.calls, "LLM should have been called once"
    user_msg = llm.calls[0]["messages"][0]["content"]
    assert "open" in user_msg


def test_classifier_rejects_unknown_episode_type():
    """VT-502-TC-003: unknown episode_type literal -> StageError."""

    payload = {
        "window_id": "w1",
        "episode_type": "definitely-cancer",
        "confidence": 0.99,
        "reasoning": "Hallucinated label.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_classification", payload)]))

    with pytest.raises(StageError):
        _run(llm)


def test_classifier_rejects_out_of_range_confidence():
    """VT-502-TC-004: confidence outside [0, 1] -> StageError."""

    payload = {
        "window_id": "w1",
        "episode_type": "cancer",
        "confidence": 1.7,
        "reasoning": "over-confident",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_classification", payload)]))

    with pytest.raises(StageError):
        _run(llm)
