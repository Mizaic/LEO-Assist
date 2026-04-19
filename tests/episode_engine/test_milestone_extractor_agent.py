"""Unit VT for the milestone extractor agent (VT-LEO-AI-503)."""

from __future__ import annotations

import pytest

from services.analysis_worker.app.episode_engine.agents import milestone_extractor
from services.analysis_worker.app.episode_engine.agents._common import StageError
from services.analysis_worker.app.episode_engine.schemas import (
    MilestoneExtractorResult,
)
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
        window_full_text="full text of the breast cancer window",
    )
    kwargs.update(overrides)
    return milestone_extractor.run(**kwargs)


def test_milestone_extractor_parses_full_payload():
    """VT-503-TC-001: a multi-milestone payload with treatment_type parses."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "referral",
                "date": "2025-03-26",
                "encounter_id": "enc-1",
                "evidence_quote": "Fast track referral for suspected breast cancer.",
                "confidence": 0.95,
                "reasoning": "Explicit 2WW referral entered by GP.",
            },
            {
                "type": "treatment_started",
                "date": "2025-07-28",
                "encounter_id": "enc-2",
                "evidence_quote": "Mastectomy of right breast (XacLJ)",
                "treatment_type": "surgery",
                "confidence": 0.95,
                "reasoning": "Definitive mastectomy.",
            },
        ],
        "needs_human_review": False,
        "reasoning": "Both milestones strongly evidenced.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))

    result, trace = _run(llm)

    assert isinstance(result, MilestoneExtractorResult)
    assert len(result.milestones) == 2
    assert result.milestones[1].treatment_type == "surgery"
    assert result.milestones[0].treatment_type is None
    assert result.needs_human_review is False
    assert trace.stage == "milestone_extractor"


def test_milestone_extractor_accepts_empty_milestones():
    """VT-503-TC-002: an empty milestone list is allowed (low evidence)."""

    payload = {
        "window_id": "w1",
        "milestones": [],
        "needs_human_review": True,
        "reasoning": "No clear evidence; flagged for human review.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    result, _ = _run(llm)

    assert result.milestones == []
    assert result.needs_human_review is True


def test_milestone_extractor_rejects_unknown_milestone_type():
    """VT-503-TC-003: an invented milestone type is rejected."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "biopsy_taken",
                "date": "2025-04-01",
                "encounter_id": "enc-1",
                "evidence_quote": "biopsy",
                "confidence": 0.8,
                "reasoning": "ad-hoc",
            }
        ],
        "needs_human_review": False,
        "reasoning": "",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    with pytest.raises(StageError):
        _run(llm)


def test_milestone_extractor_rejects_unknown_treatment_type():
    """VT-503-TC-004: invented treatment_type is rejected."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "treatment_started",
                "date": "2025-07-28",
                "encounter_id": "enc-2",
                "evidence_quote": "mastectomy",
                "treatment_type": "homeopathy",
                "confidence": 0.95,
                "reasoning": "",
            }
        ],
        "needs_human_review": False,
        "reasoning": "",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    with pytest.raises(StageError):
        _run(llm)


def test_milestone_extractor_parses_first_presentation_with_place():
    """VT-503-TC-006: first_presentation parses with a presentation_place enum."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "first_presentation",
                "date": "2025-03-12",
                "encounter_id": "enc-0",
                "evidence_quote": "Patient reports a new right breast lump.",
                "presentation_place": "gp_surgery",
                "confidence": 0.85,
                "reasoning": "GP face-to-face for the presenting symptom.",
            },
            {
                "type": "outcome_letter",
                "date": "2025-05-12",
                "encounter_id": "enc-3",
                "evidence_quote": "Breast clinic letter -- biopsy taken.",
                "confidence": 0.8,
                "reasoning": "Outcome letter received pre-diagnosis.",
            },
        ],
        "needs_human_review": False,
        "reasoning": "Two new milestones extracted.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    result, _ = _run(llm)

    assert len(result.milestones) == 2
    fp, ol = result.milestones
    assert fp.type == "first_presentation"
    assert fp.presentation_place == "gp_surgery"
    assert ol.type == "outcome_letter"
    assert ol.presentation_place is None


def test_milestone_extractor_rejects_unknown_presentation_place():
    """VT-503-TC-007: an invented presentation_place is rejected."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "first_presentation",
                "date": "2025-03-12",
                "encounter_id": "enc-0",
                "evidence_quote": "Saw GP about a lump.",
                "presentation_place": "spaceship",
                "confidence": 0.8,
                "reasoning": "",
            }
        ],
        "needs_human_review": False,
        "reasoning": "",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    with pytest.raises(StageError):
        _run(llm)


def test_milestone_extractor_parses_safety_netting_and_disruptions():
    """VT-503-TC-008: episode-level safety_netting and disruptions parse
    cleanly when the model emits them alongside milestones."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "first_presentation",
                "date": "2025-03-12",
                "encounter_id": "enc-pres",
                "evidence_quote": "Patient reports new right breast lump.",
                "presentation_place": "gp_surgery",
                "confidence": 0.9,
                "reasoning": "GP face-to-face for presenting symptom.",
            }
        ],
        "safety_netting": {
            "recorded": True,
            "evidence_quote": (
                "advised to return urgently if the lump grows or skin changes "
                "appear before the clinic appointment."
            ),
            "encounter_id": "enc-pres",
            "date": "2025-03-12",
            "confidence": 0.9,
        },
        "disruptions": [
            {
                "date": "2025-04-10",
                "category": "referral_lost_or_not_received",
                "description": (
                    "Patient phoned: no appointment letter from clinic yet."
                ),
                "encounter_id": "enc-chase",
                "evidence_quote": "no appointment letter from breast clinic yet",
                "confidence": 0.85,
            }
        ],
        "needs_human_review": False,
        "reasoning": "Captured safety netting and one disruption.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    result, _ = _run(llm)

    assert result.safety_netting is not None
    assert result.safety_netting.recorded is True
    assert result.safety_netting.encounter_id == "enc-pres"
    assert len(result.disruptions) == 1
    d = result.disruptions[0]
    assert d.category == "referral_lost_or_not_received"
    assert d.encounter_id == "enc-chase"


def test_milestone_extractor_rejects_unknown_disruption_category():
    """VT-503-TC-009: an invented disruption category is rejected."""

    payload = {
        "window_id": "w1",
        "milestones": [],
        "disruptions": [
            {
                "date": "2025-04-10",
                "category": "alien_invasion",
                "description": "anything",
                "encounter_id": "enc-1",
                "evidence_quote": "anything",
                "confidence": 0.9,
            }
        ],
        "needs_human_review": False,
        "reasoning": "",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    with pytest.raises(StageError):
        _run(llm)


def test_milestone_extractor_requires_evidence_quote():
    """VT-503-TC-005: empty evidence_quote violates min_length and is rejected."""

    payload = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "referral",
                "date": "2025-03-26",
                "encounter_id": "enc-1",
                "evidence_quote": "",
                "confidence": 0.9,
                "reasoning": "",
            }
        ],
        "needs_human_review": False,
        "reasoning": "",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload)]))
    with pytest.raises(StageError):
        _run(llm)
