"""VT-LEO-AI-522 -- Audit Relevance Filter (focus-first).

Verifies the filter that runs between the classifier and the milestone
extractor:

  * always-keep guards (cancer-coded, segmenter anchor, deterministic
    safety-netting / disruption hint) cannot be overridden by the LLM
  * Haiku batched relevance triage is invoked at most ceil(N/20) times
  * fail-open behaviour on Haiku error keeps every encounter in the
    failed batch with kept_by_fallback = true
  * audit-trace fields (input / kept-by-guard / kept-by-llm / dropped)
    are populated on the FocusedSet
  * focused set has no duplicate encounter_ids and stays in
    chronological order
  * one StageTrace per Haiku batch (the chain wires this through to the
    EpisodeEngineTrace LLMUsage stage)

Each test case below maps 1:1 to an acceptance criterion on the Atlas
verification test for "audit relevance filter" (legacy local id
VT-LEO-AI-522; look up the Atlas dcId via
compliance/atlas-migration-evidence/atlas-id-mapping.csv).
"""

from __future__ import annotations

from services.analysis_worker.app.episode_engine.agents import (
    audit_relevance_filter as audit_filter,
)
from services.analysis_worker.app.episode_engine.agents.audit_guards import (
    apply_guards,
)
from services.analysis_worker.app.episode_engine.schemas import FocusedSet
from tests.episode_engine.conftest import (
    FakeLLM,
    FakeLLMResponse,
    RaisingLLM,
    tool_use,
)

_STAGE = "audit_relevance_filter"


# -- Helpers -------------------------------------------------------------


def _enc(eid: str, date: str, text: str = "routine review") -> dict:
    return {
        "encounter_id": eid,
        "date": date,
        "text": text,
        "full_snippet": text,
    }


def _decisions(*items: tuple[str, bool, str]) -> dict:
    return {
        "decisions": [
            {"encounter_id": eid, "keep": keep, "reason": reason}
            for eid, keep, reason in items
        ]
    }


def _resp(payload: dict) -> FakeLLMResponse:
    return FakeLLMResponse(tool_uses=[tool_use("submit_relevance", payload)])


def _all_keep(encounters: list[dict], reason: str = "ok") -> dict:
    return _decisions(*[(e["encounter_id"], True, reason) for e in encounters])


# -- VT-522-TC-001 -- cancer-coded guard wins over LLM keep=False --------


def test_cancer_coded_encounter_is_kept_even_when_llm_says_drop():
    encounters = [
        _enc("e-cancer", "2025-03-26", "Histology: invasive ductal carcinoma."),
    ]
    llm = FakeLLM(
        _resp(_decisions(("e-cancer", False, "looks like routine review")))
    )

    focused, traces = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
        cancer_coded_encounter_ids=["e-cancer"],
    )

    assert isinstance(focused, FocusedSet)
    assert [e.encounter_id for e in focused.encounters] == ["e-cancer"]
    kept = focused.encounters[0]
    assert kept.kept_by_guard is True
    assert kept.guard_reason and "Cancer-coded" in kept.guard_reason
    # The encounter must NOT appear on the dropped trace.
    assert focused.report.audit_dropped_by_llm == []
    assert focused.report.audit_kept_by_guards == 1
    # Cancer-coded encounter is unguarded only by the LLM batch view, so the
    # batch still runs against it. Either way: the guard wins.
    assert all(t.stage == _STAGE for t in traces)


# -- VT-522-TC-002 -- segmenter anchor encounters are first/last and kept --


def test_first_and_last_anchor_encounters_are_preserved():
    encounters = [
        _enc("e-ref", "2025-01-10", "Refer 2WW breast lump"),
        _enc("e-mid", "2025-02-01", "Routine bp check"),
        _enc("e-tx", "2025-04-12", "Mastectomy planned"),
    ]
    llm = FakeLLM(
        _resp(
            _decisions(
                ("e-ref", False, "should be dropped but anchor wins"),
                ("e-mid", False, "routine non-cancer"),
                ("e-tx", False, "should be dropped but anchor wins"),
            )
        )
    )

    focused, _ = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
        segmenter_anchors={
            "e-ref": ["referral"],
            "e-tx": ["treatment_started"],
        },
    )

    ids = [e.encounter_id for e in focused.encounters]
    assert ids == ["e-ref", "e-tx"], "anchor encounters must survive an LLM drop"
    assert focused.encounters[0].guard_reason == "Segmenter anchor: referral"
    assert focused.encounters[1].guard_reason == "Segmenter anchor: treatment_started"
    # The middle encounter was correctly dropped by the LLM.
    dropped_ids = [d.encounter_id for d in focused.report.audit_dropped_by_llm]
    assert dropped_ids == ["e-mid"]


# -- VT-522-TC-003 -- deterministic hint guard wins ----------------------


def test_safety_netting_hint_encounter_is_kept_even_when_llm_says_drop():
    encounters = [
        _enc(
            "e-sn",
            "2025-02-15",
            "Advised to return urgently if breast lump grows or skin changes.",
        ),
        _enc("e-other", "2025-02-16", "Repeat statin script"),
    ]
    llm = FakeLLM(
        _resp(
            _decisions(
                ("e-sn", False, "looks like routine"),
                ("e-other", False, "unrelated repeat script"),
            )
        )
    )

    focused, _ = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
        hint_flagged_encounter_ids=["e-sn"],
    )

    ids = [e.encounter_id for e in focused.encounters]
    assert ids == ["e-sn"]
    assert focused.encounters[0].kept_by_guard is True
    assert focused.encounters[0].guard_reason == (
        "Safety-netting or delay hint matched in the text"
    )
    dropped_ids = [d.encounter_id for d in focused.report.audit_dropped_by_llm]
    assert dropped_ids == ["e-other"]


# -- VT-522-TC-004 -- batching shape: 25 unguarded -> 2 batches (20+5) ---


def test_haiku_triage_batches_in_groups_of_twenty():
    encounters = [_enc(f"e-{i:02d}", "2025-03-01", f"row {i}") for i in range(25)]
    first_batch = encounters[:20]
    second_batch = encounters[20:]

    llm = FakeLLM(
        [
            _resp(_all_keep(first_batch, "looks pathway-relevant")),
            _resp(_all_keep(second_batch, "looks pathway-relevant")),
        ]
    )

    focused, traces = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
    )

    assert len(llm.calls) == 2, "expected ceil(25/20) = 2 Haiku batches"
    assert len(traces) == 2
    assert all(t.stage == _STAGE for t in traces)
    assert all(t.ok for t in traces)
    assert len(focused.encounters) == 25
    assert focused.report.audit_input_encounters == 25
    assert focused.report.audit_kept_by_llm == 25
    assert focused.report.audit_kept_by_guards == 0
    assert focused.report.audit_filter_failed is False


# -- VT-522-TC-005 -- fail-open: Haiku error keeps every encounter -------


def test_fail_open_keeps_every_encounter_in_a_failed_batch():
    encounters = [_enc(f"e-{i}", "2025-03-01", f"row {i}") for i in range(3)]
    llm = RaisingLLM(RuntimeError("bedrock throttled"))

    focused, traces = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
    )

    assert len(focused.encounters) == 3
    for fe in focused.encounters:
        assert fe.kept_by_guard is False
        assert fe.kept_by_llm is True
        assert fe.kept_by_fallback is True
    assert focused.report.audit_filter_failed is True
    assert focused.report.audit_kept_by_llm == 3
    assert focused.report.audit_dropped_by_llm == []
    assert traces and traces[0].ok is False


# -- VT-522-TC-006 -- audit trace fields populated on a normal mixed run --


def test_audit_trace_fields_are_populated_on_a_mixed_run():
    encounters = [
        _enc("e-cancer", "2025-01-10", "Carcinoma in situ"),
        _enc("e-keep", "2025-02-01", "Mass in left breast"),
        _enc("e-drop", "2025-02-20", "Annual flu vaccine"),
        _enc("e-keep-2", "2025-03-12", "Suspicious mammogram"),
    ]
    payload = _decisions(
        # e-cancer bypasses the LLM (kept by guard).
        ("e-keep", True, "mentions a breast mass"),
        ("e-drop", False, "routine flu vaccination unrelated to cancer"),
        ("e-keep-2", True, "mammogram fits the suspected site"),
    )
    llm = FakeLLM(_resp(payload))

    focused, _ = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
        cancer_coded_encounter_ids=["e-cancer"],
    )

    rep = focused.report
    assert rep.audit_input_encounters == 4
    assert rep.audit_kept_by_guards == 1
    assert rep.audit_kept_by_llm == 2
    assert [d.encounter_id for d in rep.audit_dropped_by_llm] == ["e-drop"]
    assert rep.audit_filter_failed is False
    # No duplicates by encounter_id.
    ids = [e.encounter_id for e in focused.encounters]
    assert len(ids) == len(set(ids))


# -- VT-522-TC-007 -- guard + LLM keep do not duplicate -----------------


def test_guard_kept_encounter_appears_exactly_once_and_bypasses_llm():
    """DI-LEO-AI-524 (1): guarded encounters bypass the LLM entirely so
    the focused set never duplicates them, and the relevance triage call
    is skipped when every encounter is already kept by a guard."""

    encounters = [_enc("e-cancer", "2025-01-10", "Carcinoma confirmed")]
    llm = FakeLLM(_resp(_decisions(("e-cancer", True, "would have agreed"))))

    focused, traces = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
        cancer_coded_encounter_ids=["e-cancer"],
    )

    ids = [e.encounter_id for e in focused.encounters]
    assert ids == ["e-cancer"]
    only = focused.encounters[0]
    assert only.kept_by_guard is True
    assert only.kept_by_llm is None, (
        "guarded encounters must bypass the Haiku triage; the LLM never sees them"
    )
    assert only.guard_reason and "Cancer-coded" in only.guard_reason
    assert llm.calls == [], "no Haiku call should fire when all encounters are guarded"
    assert traces == []


# -- VT-522-TC-008 -- chronological order preserved ----------------------


def test_focused_set_preserves_chronological_order():
    encounters = [
        _enc("e-mar", "2025-03-26", "March entry"),
        _enc("e-jan", "2025-01-10", "January entry"),
        _enc("e-feb", "2025-02-01", "February entry"),
    ]
    llm = FakeLLM(_resp(_all_keep(encounters)))
    focused, _ = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
    )
    assert [e.encounter_id for e in focused.encounters] == [
        "e-jan",
        "e-feb",
        "e-mar",
    ]


# -- VT-522-TC-009 -- one StageTrace per batch (LLMUsage capture) --------


def test_one_stage_trace_per_haiku_batch():
    encounters = [_enc(f"e-{i:02d}", "2025-03-01") for i in range(40)]
    llm = FakeLLM(
        [
            _resp(_all_keep(encounters[:20])),
            _resp(_all_keep(encounters[20:])),
        ]
    )

    focused, traces = audit_filter.run(
        llm=llm,
        patient_id="p1",
        window_id="w1",
        suspected_site="breast",
        encounters=encounters,
    )

    assert len(traces) == 2
    for t in traces:
        assert t.stage == _STAGE
        assert t.prompt_version
        assert t.input_tokens >= 0
        assert t.output_tokens >= 0
    assert len(focused.encounters) == 40


# -- Audit guards: pure-function smoke tests ----------------------------


def test_audit_guards_returns_anchor_then_cancer_then_hint_reasons():
    """Ensures the deterministic guard surface stays stable. The chain
    relies on these reason strings appearing on the EoC audit trace."""

    encs = [
        {"encounter_id": "e-anchor"},
        {"encounter_id": "e-cancer"},
        {"encounter_id": "e-hint"},
        {"encounter_id": "e-other"},
    ]
    reasons = apply_guards(
        encounters=encs,
        segmenter_anchors={"e-anchor": ["diagnosis_confirmed"]},
        cancer_coded_encounter_ids=["e-cancer"],
        hint_flagged_encounter_ids=["e-hint"],
    )
    assert reasons == {
        "e-anchor": "Segmenter anchor: diagnosis_confirmed",
        "e-cancer": "Cancer-coded by SNOMED in the patient record",
        "e-hint": "Safety-netting or delay hint matched in the text",
    }
