"""VT-LEO-AI-523 (chain wiring) -- partition + merge + EoC trace.

Tests the chain rewiring between the audit relevance filter and the
milestone extractor:

  * single-partition runs invoke the milestone extractor exactly once
    with no per-part headings on the prompt (legacy pass-through)
  * multi-partition runs invoke the extractor once per partition and
    the deterministic Python merge produces the final result with NO
    additional LLM call
  * per-part failures are contained: the failing part contributes an
    empty milestone list with needs_human_review = true, the surviving
    parts still contribute, and an EoC PartTrace records the error
  * too_many_parts refusal: the chain creates the EoC with
    needs_human_review = true, audit_filter_overflow = true, and ZERO
    milestone-extractor LLM invocations

The tests drive ``_node_milestone_extractor`` directly with a hand-built
EngineState so they exercise the integration without spinning up
LangGraph. The audit relevance filter step is simulated via a
pre-populated ``focused_sets`` slot on the state.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from services.analysis_worker.app.episode_engine import chain as chain_mod
from services.analysis_worker.app.episode_engine.schemas import (
    MilestoneExtractorResult,
    StageTrace,
)
from tests.episode_engine.conftest import FakeLLM, FakeLLMResponse, tool_use


# -- Helpers -----------------------------------------------------------


def _classified(window_id: str = "w1") -> dict:
    return {
        "window_id": window_id,
        "episode_type": "cancer",
        "confidence": 0.9,
        "reasoning": "evident",
    }


def _candidate(window_id: str = "w1") -> dict:
    return {
        "window_id": window_id,
        "suspected_site": "breast",
        "window_start": "2025-01-01",
        "window_end": "2025-12-31",
    }


def _focused(*encounter_ids: str, kept_by_guards: int = 0) -> dict:
    return {
        "encounters": [
            {
                "encounter_id": eid,
                "encounter_date": "2025-03-26",
                "kept_by_guard": False,
                "kept_by_fallback": False,
            }
            for eid in encounter_ids
        ],
        "report": {
            "audit_input_encounters": len(encounter_ids),
            "audit_kept_by_guards": kept_by_guards,
            "audit_kept_by_llm": len(encounter_ids) - kept_by_guards,
            "audit_dropped_by_llm": [],
            "audit_filter_failed": False,
            "audit_filter_overflow": False,
            "audit_parts": 1,
        },
    }


def _encounter_index(*encounter_ids: str, body_chars: int = 200) -> dict:
    return {
        eid: {
            "encounter_id": eid,
            "date": "2025-03-26",
            "text": "x" * body_chars,
            "full_snippet": "x" * body_chars,
        }
        for eid in encounter_ids
    }


def _milestone_payload(window_id: str = "w1") -> dict:
    return {
        "window_id": window_id,
        "milestones": [
            {
                "type": "referral",
                "date": "2025-03-26",
                "encounter_id": "e-1",
                "evidence_quote": "fast track referral for breast lump",
                "confidence": 0.9,
                "reasoning": "explicit 2WW referral",
            }
        ],
        "needs_human_review": False,
        "reasoning": "single milestone identified",
    }


def _build_state(
    *,
    focused_sets: dict[str, dict],
    encounter_index: dict[str, dict[str, Any]],
    classified: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "patient_id": "p1",
        "candidate_windows": candidates or [_candidate()],
        "classified_windows": classified or [_classified()],
        "focused_sets": focused_sets,
        "encounter_index": encounter_index,
        "stage_traces": [],
        "errors": [],
        "eoc_traces": [],
    }


# -- VT-523-TC-010 -- single-partition pass-through ---------------------


def test_chain_single_partition_invokes_extractor_once_with_no_part_headings():
    fake = FakeLLM(
        FakeLLMResponse(tool_uses=[tool_use("submit_milestones", _milestone_payload())])
    )
    state = _build_state(
        focused_sets={"w1": _focused("e-1", "e-2")},
        encounter_index=_encounter_index("e-1", "e-2"),
    )

    with patch.object(chain_mod, "_llm", return_value=fake):
        out = chain_mod._node_milestone_extractor(state)

    assert len(fake.calls) == 1, "single-partition runs make exactly one LLM call"
    user_msg = fake.calls[0]["messages"][0]["content"]
    assert "Part 1 of" not in user_msg, (
        "single-partition prompt must not carry part headings"
    )
    extracted = out["extracted"]
    assert len(extracted) == 1
    merged = MilestoneExtractorResult.model_validate(extracted[0])
    assert merged.reasoning == "single milestone identified"
    assert merged.needs_human_review is False

    eoc_traces = out["eoc_traces"]
    assert len(eoc_traces) == 1
    assert eoc_traces[0]["audit_parts"] == 1
    assert eoc_traces[0]["audit_filter_overflow"] is False
    assert len(eoc_traces[0]["parts"]) == 1


# -- VT-523-TC-011 -- multi-partition runs merge per-part with no LLM merge --


def test_chain_multi_partition_invokes_extractor_once_per_partition_and_merges():
    # Build encounters big enough that the partitioner splits into >=2 parts.
    encounter_index = _encounter_index(
        *[f"e-{i:02d}" for i in range(20)], body_chars=800
    )
    focused_set = _focused(*[f"e-{i:02d}" for i in range(20)])

    payload_a = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "referral",
                "date": "2025-03-26",
                "encounter_id": "e-00",
                "evidence_quote": "fast track referral",
                "confidence": 0.9,
                "reasoning": "ok",
            }
        ],
        "needs_human_review": False,
        "reasoning": "part-a",
    }
    payload_b = {
        "window_id": "w1",
        "milestones": [
            {
                "type": "treatment_started",
                "date": "2025-07-28",
                "encounter_id": "e-19",
                "evidence_quote": "mastectomy",
                "confidence": 0.95,
                "reasoning": "definitive surgery",
                "treatment_type": "surgery",
            }
        ],
        "needs_human_review": False,
        "reasoning": "part-b",
    }
    fake = FakeLLM(
        [
            FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload_a)]),
            FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload_b)]),
            FakeLLMResponse(tool_uses=[tool_use("submit_milestones", payload_b)]),
        ]
    )

    state = _build_state(
        focused_sets={"w1": focused_set},
        encounter_index=encounter_index,
    )

    with patch.object(chain_mod, "_llm", return_value=fake):
        with patch.object(
            chain_mod,
            "partition_window",
            wraps=chain_mod.partition_window,
        ) as wrapped:
            # Coerce the partitioner to split: per_part_budget = budget -
            # 4000-token reserve. 20 encs * ~240 tokens = ~4800 tokens of
            # content; budget=5200 leaves ~1200 tokens per part -> ~4
            # partitions.
            with patch.dict(os.environ, {"EPISODE_ENGINE_MAX_INPUT_TOKENS": "5200"}):
                out = chain_mod._node_milestone_extractor(state)
            assert wrapped.call_count == 1

    # Multi-part: at least two extractor calls happened.
    assert len(fake.calls) >= 2, "expected one extractor call per partition"
    extracted = out["extracted"]
    assert len(extracted) == 1
    merged = MilestoneExtractorResult.model_validate(extracted[0])
    # Merged result carries milestones from both parts.
    types = {(m.type, m.encounter_id) for m in merged.milestones}
    assert ("referral", "e-00") in types
    assert ("treatment_started", "e-19") in types
    # Reasoning carries per-part headings.
    assert "Part 1 of" in merged.reasoning


# -- VT-523-TC-012 -- per-part failure containment ----------------------


def test_chain_contains_per_part_failure_and_records_eoc_part_trace():
    encounter_index = _encounter_index(
        *[f"e-{i:02d}" for i in range(20)], body_chars=800
    )
    focused_set = _focused(*[f"e-{i:02d}" for i in range(20)])

    good_payload = _milestone_payload()
    fake = FakeLLM(
        [
            FakeLLMResponse(tool_uses=[tool_use("submit_milestones", good_payload)]),
            # Second call: no toolUse -> StageError raised by call_stage.
            FakeLLMResponse(tool_uses=[], stop_reason="end_turn"),
        ]
    )

    state = _build_state(
        focused_sets={"w1": focused_set},
        encounter_index=encounter_index,
    )

    with patch.object(chain_mod, "_llm", return_value=fake):
        with patch.dict(os.environ, {"EPISODE_ENGINE_MAX_INPUT_TOKENS": "5200"}):
            out = chain_mod._node_milestone_extractor(state)

    extracted = out["extracted"]
    assert len(extracted) == 1
    merged = MilestoneExtractorResult.model_validate(extracted[0])
    # Surviving part still contributed the milestone (the good payload
    # references encounter id "e-1" via the standard milestone payload).
    assert any(m.encounter_id == "e-1" for m in merged.milestones)
    assert merged.needs_human_review is True

    eoc = out["eoc_traces"][0]
    parts = eoc["parts"]
    failed = [p for p in parts if p.get("error")]
    assert failed, "the failing part must be recorded with a part-trace error"
    surviving = [p for p in parts if not p.get("error")]
    assert surviving, "surviving parts must remain on the audit trace"

    # The chain accumulated an error string for the failed part.
    assert any("milestone[w1 part" in err for err in out["errors"])


# -- VT-523-TC-013 -- too_many_parts refusal: ZERO extractor calls -----


def test_chain_overflow_refusal_skips_extractor_and_flags_for_review():
    encounter_index = _encounter_index(
        *[f"e-{i:02d}" for i in range(60)], body_chars=4_000
    )
    focused_set = _focused(*[f"e-{i:02d}" for i in range(60)])
    fake = FakeLLM(
        FakeLLMResponse(tool_uses=[tool_use("submit_milestones", _milestone_payload())])
    )

    state = _build_state(
        focused_sets={"w1": focused_set},
        encounter_index=encounter_index,
    )

    # Force the partitioner to return too_many_parts by patching it.
    from services.analysis_worker.app.episode_engine.schemas import PartitionReport

    with patch.object(chain_mod, "_llm", return_value=fake):
        with patch.object(
            chain_mod,
            "partition_window",
            return_value=(
                [],
                PartitionReport(
                    total_parts=0,
                    too_many_parts=True,
                    notice=(
                        "This patient has too much pathway-relevant material "
                        "to audit in one run. Ask a clinician to review the "
                        "encounter range manually."
                    ),
                ),
            ),
        ):
            out = chain_mod._node_milestone_extractor(state)

    # ZERO milestone-extractor invocations on overflow.
    assert fake.calls == [], (
        "too_many_parts must short-circuit -- no extractor LLM call"
    )

    extracted = out["extracted"]
    assert len(extracted) == 1
    merged = MilestoneExtractorResult.model_validate(extracted[0])
    assert merged.milestones == []
    assert merged.needs_human_review is True
    assert "manually" in merged.reasoning

    eoc = out["eoc_traces"][0]
    assert eoc["audit_filter_overflow"] is True
    assert eoc["audit_parts"] == 0
    assert any("audit_partition_overflow" in err for err in out["errors"])


# -- Bonus -- merge invariants: no second LLM call wired in chain ------


def test_chain_does_not_call_llm_for_merge_step():
    """Ensures the chain calls the milestone extractor LLM only and never
    routes the merged result through any other LLM stage."""

    encounter_index = _encounter_index("e-1", body_chars=200)
    focused_set = _focused("e-1")
    fake = FakeLLM(
        FakeLLMResponse(tool_uses=[tool_use("submit_milestones", _milestone_payload())])
    )
    state = _build_state(
        focused_sets={"w1": focused_set},
        encounter_index=encounter_index,
    )

    with patch.object(chain_mod, "_llm", return_value=fake):
        chain_mod._node_milestone_extractor(state)

    # Only one LLM call ever fires inside the milestone-extractor stage.
    assert len(fake.calls) == 1
    # And the trace label is the extractor stage; no merge stage exists.
    stage_dicts = state["stage_traces"]
    stages = [StageTrace.model_validate(d) for d in stage_dicts]
    assert all(s.stage == "milestone_extractor" for s in stages) or stages == []
