"""Unit VT for the reconciler agent (VT-LEO-AI-504)."""

from __future__ import annotations

import json

from services.analysis_worker.app.episode_engine.agents import reconciler
from services.analysis_worker.app.episode_engine.schemas import ReconcilerResult
from tests.episode_engine.conftest import (
    FakeLLM,
    FakeLLMResponse,
    tool_use,
)


_CANDIDATES = [
    {
        "window_id": "w1",
        "suspected_site": "breast",
        "window_start": "2025-03-26",
        "window_end": "2025-07-28",
        "episode_type": "cancer",
        "confidence": 0.93,
        "milestones": [
            {
                "type": "referral",
                "date": "2025-03-26",
                "encounter_id": "enc-1",
                "evidence_quote": "Fast track referral.",
                "confidence": 0.95,
                "reasoning": "",
            }
        ],
    }
]


def test_reconciler_parses_single_episode():
    """VT-504-TC-001: reconciler returns ReconciledEpisode list."""

    payload = {
        "episodes": [
            {
                "episode_id": "e-1",
                "suspected_site": "breast",
                "episode_type": "cancer",
                "window_start": "2025-03-26",
                "window_end": "2025-07-28",
                "milestones": [
                    {
                        "type": "referral",
                        "date": "2025-03-26",
                        "encounter_id": "enc-1",
                        "evidence_quote": "Fast track referral.",
                        "confidence": 0.95,
                        "reasoning": "",
                    }
                ],
                "confidence": 0.93,
                "reasoning": "Single confirmed breast cancer episode.",
                "needs_human_review": False,
                "merged_from": ["w1"],
            }
        ],
        "notes": "No merges needed.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_episodes", payload)]))

    result, trace = reconciler.run(
        llm=llm, patient_id="p-1", candidates=_CANDIDATES
    )

    assert isinstance(result, ReconcilerResult)
    assert len(result.episodes) == 1
    ep = result.episodes[0]
    assert ep.episode_id == "e-1"
    assert ep.merged_from == ["w1"]
    assert ep.needs_human_review is False
    assert trace.stage == "reconciler"


def test_reconciler_serialises_candidates_as_json():
    """VT-504-TC-002: candidates are passed to the LLM as JSON in the user msg."""

    payload = {"episodes": [], "notes": "nothing"}
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_episodes", payload)]))

    reconciler.run(llm=llm, patient_id="p-1", candidates=_CANDIDATES)

    user_msg = llm.calls[0]["messages"][0]["content"]
    assert "p-1" in user_msg
    assert "w1" in user_msg
    parsed_window = json.loads(
        user_msg[user_msg.index("[") : user_msg.rindex("]") + 1]
    )
    assert parsed_window[0]["window_id"] == "w1"


def test_reconciler_supports_multi_to_one_merge():
    """VT-504-TC-003: a multi-window merge response parses cleanly."""

    payload = {
        "episodes": [
            {
                "episode_id": "e-merge",
                "suspected_site": "breast",
                "episode_type": "multi_site",
                "window_start": "2025-03-26",
                "window_end": "2025-07-28",
                "milestones": [],
                "confidence": 0.9,
                "reasoning": "Two referral windows for the same diagnosis.",
                "needs_human_review": False,
                "merged_from": ["w1", "w2"],
            }
        ],
        "notes": "Merged two windows that resolved to one breast cancer.",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_episodes", payload)]))

    result, _ = reconciler.run(llm=llm, patient_id="p-1", candidates=_CANDIDATES)
    assert result.episodes[0].merged_from == ["w1", "w2"]
    assert result.episodes[0].episode_type == "multi_site"


def test_reconciler_preserves_safety_netting_and_disruptions():
    """VT-504-TC-004: episode-level safety_netting and disruptions
    survive the reconciler round-trip."""

    payload = {
        "episodes": [
            {
                "episode_id": "e-1",
                "suspected_site": "breast",
                "episode_type": "cancer",
                "window_start": "2025-03-26",
                "window_end": "2025-07-28",
                "milestones": [
                    {
                        "type": "referral",
                        "date": "2025-03-26",
                        "encounter_id": "enc-1",
                        "evidence_quote": "Fast track referral.",
                        "confidence": 0.95,
                        "reasoning": "",
                    }
                ],
                "safety_netting": {
                    "recorded": True,
                    "evidence_quote": "advised to return if lump grows.",
                    "encounter_id": "enc-pres",
                    "date": "2025-03-12",
                    "confidence": 0.9,
                },
                "disruptions": [
                    {
                        "date": "2025-04-10",
                        "category": "referral_lost_or_not_received",
                        "description": "Patient phoned -- no clinic letter.",
                        "encounter_id": "enc-chase",
                        "evidence_quote": "no appointment letter from clinic",
                        "confidence": 0.85,
                    }
                ],
                "confidence": 0.93,
                "reasoning": "preserved",
                "needs_human_review": False,
                "merged_from": ["w1"],
            }
        ],
        "notes": "preserved",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_episodes", payload)]))
    result, _ = reconciler.run(llm=llm, patient_id="p-1", candidates=_CANDIDATES)
    ep = result.episodes[0]
    assert ep.safety_netting is not None
    assert ep.safety_netting.recorded is True
    assert ep.safety_netting.encounter_id == "enc-pres"
    assert len(ep.disruptions) == 1
    assert ep.disruptions[0].category == "referral_lost_or_not_received"
