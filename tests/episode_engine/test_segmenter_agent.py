"""Unit VT for the segmenter agent (VT-LEO-AI-501)."""

from __future__ import annotations

import pytest

from services.analysis_worker.app.episode_engine.agents import segmenter
from services.analysis_worker.app.episode_engine.agents._common import (
    StageError,
    build_tool_config,
)
from services.analysis_worker.app.episode_engine.schemas import SegmenterResult
from tests.episode_engine.conftest import (
    FakeLLM,
    FakeLLMResponse,
    RaisingLLM,
    tool_use,
    tool_use_str,
)

_VALID_PAYLOAD = {
    "windows": [
        {
            "window_id": "w1",
            "suspected_site": "breast",
            "window_start": "2025-03-26",
            "window_end": "2025-07-28",
            "rationale": "2WW referral followed by clinic and treatment.",
        },
        {
            "window_id": "w2",
            "suspected_site": "skin",
            "window_start": "2024-10-01",
            "rationale": "Suspicious lesion biopsy followed by excision.",
        },
    ],
    "notes": "Two distinct cancer windows identified.",
}


def _run_segmenter(llm: FakeLLM | RaisingLLM):
    return segmenter.run(
        llm=llm,
        patient_id="p-1",
        timeline_text="== 2025-03-26 (1 record) ==\n  [aaa] Fast track referral",
    )


def test_segmenter_parses_valid_tool_use():
    """VT-501-TC-001: a well-formed toolUse is parsed into SegmenterResult."""

    llm = FakeLLM(
        FakeLLMResponse(
            tool_uses=[tool_use("submit_windows", _VALID_PAYLOAD)],
            input_tokens=2000,
            output_tokens=120,
        )
    )

    result, trace = _run_segmenter(llm)

    assert isinstance(result, SegmenterResult)
    assert len(result.windows) == 2
    assert {w.window_id for w in result.windows} == {"w1", "w2"}
    assert trace.stage == "segmenter"
    assert trace.prompt_version == "v1"
    assert trace.input_tokens == 2000
    assert trace.output_tokens == 120
    assert trace.ok is True


def test_segmenter_accepts_string_tool_input():
    """VT-501-TC-002: toolUse.input may be a JSON string and is still parsed."""

    llm = FakeLLM(
        FakeLLMResponse(tool_uses=[tool_use_str("submit_windows", _VALID_PAYLOAD)])
    )

    result, trace = _run_segmenter(llm)
    assert len(result.windows) == 2
    assert trace.ok is True


def test_segmenter_raises_when_tool_use_missing():
    """VT-501-TC-003: empty tool_uses -> StageError, no parse."""

    llm = FakeLLM(FakeLLMResponse(tool_uses=[], stop_reason="end_turn"))

    with pytest.raises(StageError):
        _run_segmenter(llm)


def test_segmenter_raises_on_schema_violation():
    """VT-501-TC-004: invalid payload (bad date) -> StageError."""

    bad = {
        "windows": [
            {
                "window_id": "w1",
                "suspected_site": "breast",
                "window_start": "not-a-date",
                "rationale": "broken",
            }
        ],
        "notes": "",
    }
    llm = FakeLLM(FakeLLMResponse(tool_uses=[tool_use("submit_windows", bad)]))

    with pytest.raises(StageError):
        _run_segmenter(llm)


def test_segmenter_raises_when_llm_call_fails():
    """VT-501-TC-005: provider-level exception is wrapped in StageError."""

    llm = RaisingLLM(RuntimeError("bedrock down"))
    with pytest.raises(StageError, match="LLM call failed"):
        _run_segmenter(llm)


def test_build_tool_config_forces_tool_choice():
    """VT-501-TC-006: tool_config forces the tool choice (forced JSON)."""

    cfg = build_tool_config("submit_windows", {"type": "object"})
    assert cfg["toolChoice"] == {"tool": {"name": "submit_windows"}}
    assert cfg["tools"][0]["toolSpec"]["name"] == "submit_windows"
    assert cfg["tools"][0]["toolSpec"]["inputSchema"] == {"json": {"type": "object"}}


def test_segmenter_prompt_multisite_heuristics_present():
    """VT-501-TC-007: SYSTEM prompt has multi-site and GP-investigation heuristics.

    Regression guard: ensures the three new boundary clauses added in W-018
    remediation are not accidentally dropped from the prompt. A missing clause
    causes the LLM to merge GP-only investigation windows or same-day multi-site
    2WW referrals into a single window.
    """
    from libs.prompts.episode_engine import segmenter_v1

    assert (
        "GP-ONLY INVESTIGATION WINDOWS" in segmenter_v1.SYSTEM
    ), "Missing GP-only investigation heuristic -- Lung benign window will be dropped"
    assert "SHARED FIRST PRESENTATION" in segmenter_v1.SYSTEM, (
        "Missing shared-first-presentation heuristic -- multi-site presentations "
        "will be collapsed into a single window"
    )
    assert "SAME-DAY MULTI-SITE 2WW REFERRALS" in segmenter_v1.SYSTEM, (
        "Missing same-day multi-site 2WW heuristic -- Breast and Upper GI "
        "windows will be merged when both 2WW forms are submitted on the same day"
    )
    assert "SYN-EE-002" in segmenter_v1.SYSTEM, (
        "Missing multi-site reference case (SYN-EE-002) -- LLM will fuse "
        "a GP-only Lung window into an Oesophageal window"
    )
    assert "A&E / HOSPITAL-FIRST ENTRY" in segmenter_v1.SYSTEM, (
        "Missing A&E / hospital-first heuristic -- patients with no prior "
        "GP 2WW will not get a window from ED or acute admission"
    )
    assert "SYN-EE-003" in segmenter_v1.SYSTEM, (
        "Missing colorectal same-day screening + malignancy reference -- "
        "segmenter may set window_start after the first screening contact"
    )
    assert "SYN-EE-004" in segmenter_v1.SYSTEM, (
        "Missing BCSP/FOBT first-presentation reference (SYN-EE-004) -- "
        "screen-detected rows without GP will not set window_start"
    )
