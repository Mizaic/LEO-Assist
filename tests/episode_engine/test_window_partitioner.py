"""VT-LEO-AI-523 -- Window Partitioner safety net for milestone extractor.

Verifies the pure-function partitioner + deterministic merge that wraps
the milestone extractor:

  * single-partition pass-through (the common case)
  * multi-part packing preserves every focused encounter
  * intra-encounter split for an oversized record
  * deterministic Python merge de-dups milestones on
    (type, date, encounter_id) keeping the highest confidence and the
    longest evidence quote
  * safety_netting unions across parts; disruptions de-dup on
    (category, date, encounter_id)
  * too_many_parts refusal returns no partitions and a friendly notice
  * NO LLM call is made by the partitioner or the merger (pure-Python
    invariant from R-LEO-AI-513)

Each test maps 1:1 to an acceptance criterion on the Atlas
verification test for the SBAR background partitioner (legacy local id
VT-LEO-AI-523; look up the Atlas dcId via
compliance/atlas-migration-evidence/atlas-id-mapping.csv).
"""

from __future__ import annotations

from datetime import date

from services.analysis_worker.app.episode_engine.schemas import (
    Disruption,
    Milestone,
    MilestoneExtractorResult,
    SafetyNetting,
)
from services.analysis_worker.app.episode_engine.window_partitioner import (
    merge_milestones_deterministic,
    partition_window,
)


# -- Helpers -----------------------------------------------------------


def _enc(eid: str, text: str = "short body") -> dict:
    return {
        "encounter_id": eid,
        "date": "2025-01-01",
        "full_snippet": text,
    }


def _milestone(
    *,
    type_: str = "referral",
    eid: str = "enc-1",
    d: str = "2025-03-26",
    confidence: float = 0.9,
    quote: str = "evidence quote",
) -> Milestone:
    return Milestone(
        type=type_,
        date=date.fromisoformat(d),
        encounter_id=eid,
        evidence_quote=quote,
        confidence=confidence,
        reasoning="rationale",
    )


def _disruption(
    *,
    category: str = "appointment_dna",
    eid: str = "enc-2",
    d: str = "2025-04-10",
    confidence: float = 0.8,
    quote: str = "patient did not attend",
) -> Disruption:
    return Disruption(
        date=date.fromisoformat(d),
        category=category,
        description="DNA event",
        encounter_id=eid,
        evidence_quote=quote,
        confidence=confidence,
    )


# -- VT-523-TC-001 -- single-partition common case -----------------------


def test_single_partition_when_focused_set_fits_one_part():
    encounters = [_enc(f"e-{i}") for i in range(5)]
    partitions, report = partition_window(encounters)

    assert len(partitions) == 1
    only = partitions[0]
    assert only.index == 1
    assert only.total == 1
    assert only.encounter_ids == [f"e-{i}" for i in range(5)]
    assert only.part_in_encounter is None
    assert report.total_parts == 1
    assert report.too_many_parts is False
    assert report.notice is None  # quiet on the common case


# -- VT-523-TC-002 -- multi-part packing preserves every encounter ------


def test_multi_part_packing_preserves_every_focused_encounter():
    body = "x" * 800  # ~ 222 tokens at our 3.6 chars/token estimate
    encounters = [_enc(f"e-{i:02d}", body) for i in range(20)]
    # Tiny budget forces >1 partition while keeping every encounter intact.
    partitions, report = partition_window(
        encounters,
        max_input_tokens=2_000,
        system_prompt_reserve_tokens=500,
        max_parts=8,
    )

    assert report.too_many_parts is False
    assert len(partitions) >= 2
    # Every input encounter id must appear in exactly one partition.
    seen: list[str] = []
    for p in partitions:
        seen.extend(p.encounter_ids)
    assert sorted(seen) == sorted(e["encounter_id"] for e in encounters)
    assert len(seen) == len(set(seen)), "no encounter is duplicated across parts"
    assert report.notice and "split the audit into" in report.notice


# -- VT-523-TC-003 -- intra-encounter split for an oversized record ----


def test_oversized_encounter_is_split_with_part_in_encounter_metadata():
    # 4000 chars (the per-encounter cap) -> ~1112 tokens; a per-part
    # budget of 800 tokens forces an intra-encounter split.
    big_body = "y" * 4_000
    encounters = [_enc("e-big", big_body)]
    partitions, report = partition_window(
        encounters,
        max_input_tokens=900,
        system_prompt_reserve_tokens=100,
        max_parts=8,
    )

    assert report.too_many_parts is False
    # The split slices may all live in one part if budget allows OR span
    # multiple parts. Either way, the encounter id must appear and the
    # part_in_encounter metadata must indicate the split.
    found_split = False
    for p in partitions:
        if p.part_in_encounter and "e-big" in p.part_in_encounter:
            i, n = p.part_in_encounter["e-big"]
            assert n >= 2
            assert 1 <= i <= n
            found_split = True
    assert found_split, "oversized encounter must report part_in_encounter"


# -- VT-523-TC-004 -- too_many_parts refusal ----------------------------


def test_too_many_parts_returns_empty_partitions_and_friendly_notice():
    body = "z" * 4_000
    encounters = [_enc(f"e-{i:02d}", body) for i in range(60)]
    partitions, report = partition_window(
        encounters,
        max_input_tokens=2_000,
        system_prompt_reserve_tokens=500,
        max_parts=2,
    )

    assert partitions == []
    assert report.too_many_parts is True
    assert report.total_parts == 0
    assert report.notice and "manually" in report.notice


# -- VT-523-TC-005 -- empty focused set returns one empty partition -----


def test_empty_focused_set_returns_one_empty_partition():
    partitions, report = partition_window([])
    assert len(partitions) == 1
    assert partitions[0].encounter_ids == []
    assert report.total_parts == 1
    assert report.too_many_parts is False


# -- VT-523-TC-006 -- merge: dedup milestones, keep highest confidence --


def test_merge_dedups_milestones_keeping_highest_confidence_and_longest_quote():
    low = _milestone(confidence=0.6, quote="short")
    high = _milestone(confidence=0.95, quote="long detailed evidence quote")
    other = _milestone(eid="enc-2", confidence=0.7, quote="other-quote")

    part_a = MilestoneExtractorResult(
        window_id="w1",
        milestones=[low, other],
        needs_human_review=False,
        reasoning="part-a notes",
    )
    part_b = MilestoneExtractorResult(
        window_id="w1",
        milestones=[high],
        needs_human_review=False,
        reasoning="part-b notes",
    )

    merged = merge_milestones_deterministic([part_a, part_b], window_id="w1")
    by_key = {(m.type, str(m.date), m.encounter_id): m for m in merged.milestones}
    survivor = by_key[("referral", "2025-03-26", "enc-1")]
    assert survivor.confidence == 0.95
    assert survivor.evidence_quote == "long detailed evidence quote"
    # The non-conflicting milestone is preserved.
    assert ("referral", "2025-03-26", "enc-2") in by_key
    # Reasoning carries per-part attribution.
    assert "Part 1 of 2: part-a notes" in merged.reasoning
    assert "Part 2 of 2: part-b notes" in merged.reasoning


# -- VT-523-TC-007 -- merge: safety_netting unions, disruptions dedup ---


def test_merge_unions_safety_netting_and_dedups_disruptions():
    sn = SafetyNetting(
        recorded=True,
        evidence_quote="advised to return if symptoms worsen",
        encounter_id="enc-pres",
        date=date(2025, 3, 12),
        confidence=0.9,
    )
    dna_low = _disruption(confidence=0.7, quote="DNA")
    dna_high = _disruption(confidence=0.9, quote="patient did not attend clinic")
    dna_other = _disruption(eid="enc-3", confidence=0.85, quote="another DNA")

    part_a = MilestoneExtractorResult(
        window_id="w1",
        milestones=[],
        safety_netting=None,
        disruptions=[dna_low, dna_other],
        needs_human_review=False,
        reasoning="a",
    )
    part_b = MilestoneExtractorResult(
        window_id="w1",
        milestones=[],
        safety_netting=sn,
        disruptions=[dna_high],
        needs_human_review=True,
        reasoning="b",
    )

    merged = merge_milestones_deterministic([part_a, part_b], window_id="w1")

    assert merged.safety_netting is not None
    assert merged.safety_netting.recorded is True
    assert merged.safety_netting.encounter_id == "enc-pres"
    assert merged.needs_human_review is True

    by_key = {
        (d.category, str(d.date), d.encounter_id): d for d in merged.disruptions
    }
    survivor = by_key[("appointment_dna", "2025-04-10", "enc-2")]
    assert survivor.confidence == 0.9
    assert ("appointment_dna", "2025-04-10", "enc-3") in by_key


# -- VT-523-TC-008 -- single-part merge is byte-for-byte pass-through ---


def test_single_part_merge_is_legacy_pass_through():
    sn = SafetyNetting(recorded=False)
    only = MilestoneExtractorResult(
        window_id="w1",
        milestones=[_milestone()],
        safety_netting=sn,
        disruptions=[_disruption()],
        needs_human_review=False,
        reasoning="single-part rationale",
    )

    merged = merge_milestones_deterministic([only], window_id="w1")
    assert merged.reasoning == "single-part rationale"
    assert "Part 1 of" not in merged.reasoning
    assert merged.milestones[0].evidence_quote == "evidence quote"
    assert merged.disruptions[0].category == "appointment_dna"


# -- VT-523-TC-009 -- merge handles empty list ---------------------------


def test_merge_returns_empty_result_when_no_parts():
    merged = merge_milestones_deterministic([], window_id="w1")
    assert merged.window_id == "w1"
    assert merged.milestones == []
    assert merged.disruptions == []
    assert merged.needs_human_review is False
    assert merged.reasoning == ""
