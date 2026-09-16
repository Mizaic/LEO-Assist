"""VT-LEO-AI-514 TC-010 / TC-011 / TC-012 / TC-013: Background partitioner.

Verifies the partitioner:
  - Returns a single partition when sources fit under budget (TC-010).
  - Splits sources into N <= 8 partitions when they do not fit, with
    every record preserved across the partitions (no-record-dropped
    invariant) (TC-011).
  - Splits one over-budget record across slices labelled
    ``part_in_record`` so the LLM can treat the slices as halves of
    the same source (TC-012).
  - Refuses with too_many_parts=True when more than max_parts would
    be needed, returning an empty partitions list so the caller
    surfaces a friendly error (TC-013).

See DI-LEO-AI-513 / DI-LEO-AI-517 / DO-LEO-AI-515 / DO-LEO-AI-517.
"""

from __future__ import annotations

import json
import re

from libs.sbar.background_partitioner import (
    _estimate_tokens,
    partition_background_sources,
)
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource


def _make_source(idx: int, *, text_len: int) -> ResolvedSource:
    return ResolvedSource(
        source_label="Encounter",
        source_id=f"enc-{idx}",
        text="x" * text_len,
        codes=[],
        metadata={},
    )


def _all_source_ids_in_partitions(partitions) -> set[str]:
    out: set[str] = set()
    for p in partitions:
        for d in p.descriptors:
            out.add(d.source_id)
    return out


def test_partitioner_returns_one_partition_when_under_budget() -> None:
    sources = [_make_source(i, text_len=200) for i in range(3)]
    parts, report = partition_background_sources(
        sources, [], referring_specialty=None, max_input_tokens=60000
    )

    assert len(parts) == 1
    assert parts[0].index == 1
    assert parts[0].total == 1
    assert report.total_records == 3
    assert report.total_parts == 1
    assert report.too_many_parts is False
    assert report.notice is None
    assert report.split_records == []
    assert _all_source_ids_in_partitions(parts) == {"enc-0", "enc-1", "enc-2"}


def test_descriptor_full_text_carries_the_exact_llm_prompt_text() -> None:
    """A reviewer must be able to see exactly what the LLM saw.

    ``full_text`` on the descriptor is the sanitised, capped text for
    this slice -- not just the 200-char ``preview``. It must match the
    text this source actually contributed to the partition's LLM
    prompt (modulo the fixed CONTEXT JSON wrapper).
    """
    sources = [_make_source(0, text_len=300)]
    parts, _ = partition_background_sources(
        sources, [], referring_specialty=None, max_input_tokens=60000
    )
    descriptor = parts[0].descriptors[0]
    assert descriptor.full_text == "x" * 300
    assert descriptor.full_text in parts[0].user_message
    # preview stays short even though full_text is not.
    assert len(descriptor.preview) <= 200


def test_partitioner_splits_into_multiple_parts_preserving_every_source() -> None:
    # 12 sources of 4000 chars each -- total ~48KB of source text. With
    # a tight 8000-token budget (after 4000 reserve = 4000 effective)
    # we need multiple parts.
    sources = [_make_source(i, text_len=4000) for i in range(12)]

    parts, report = partition_background_sources(
        sources,
        [],
        referring_specialty=None,
        max_input_tokens=8000,
        system_prompt_reserve_tokens=4000,
    )

    assert report.too_many_parts is False
    assert len(parts) >= 2
    assert len(parts) <= 8
    assert report.total_parts == len(parts)
    assert report.notice and "summarised them in" in report.notice

    # NO RECORD DROPPED invariant: every input source MUST appear
    # in some partition.
    assert _all_source_ids_in_partitions(parts) == {f"enc-{i}" for i in range(12)}

    # Each partition's user_message must include the part header so
    # the LLM knows it is summarising one chunk of a multi-part run.
    for part in parts:
        assert f'"index": {part.index}' in part.user_message
        assert f'"total": {part.total}' in part.user_message


def test_partitioner_splits_one_oversize_record_across_slices() -> None:
    # One single record that is far too long to fit in one part on
    # its own (60K chars when capped at 4000) forces intra-record
    # splitting.
    big = ResolvedSource(
        source_label="Document",
        source_id="doc-big",
        text="y" * 60000,
        codes=[],
        metadata={},
    )

    parts, report = partition_background_sources(
        [big],
        [],
        referring_specialty=None,
        max_input_tokens=2000,
        system_prompt_reserve_tokens=1000,
    )

    assert "doc-big" in report.split_records
    assert report.record_split_notice and "doc-big" in report.record_split_notice

    # The single record must appear across two or more slices, each
    # tagged with part_in_record so the LLM can treat them as
    # halves of the same source.
    slice_descriptors = [d for p in parts for d in p.descriptors]
    big_slices = [d for d in slice_descriptors if d.source_id == "doc-big"]
    assert len(big_slices) >= 2
    assert {d.slice_total for d in big_slices} == {len(big_slices)}
    assert sorted(d.slice_index for d in big_slices) == list(
        range(1, len(big_slices) + 1)
    )

    # Confirm part_in_record markers appear in the user message.
    for p in parts:
        if any(d.source_id == "doc-big" for d in p.descriptors):
            assert "part_in_record" in p.user_message


def test_partitioner_not_blocked_when_all_codes_exceed_budget() -> None:
    # Regression: a patient with 19 sources and 76 coded facts used to
    # produce too_many_parts because all codes were duplicated into every
    # partition's fixed overhead, making the overhead (72k tokens) exceed
    # the entire budget (60k). The fix is to calculate packing overhead
    # without codes and filter codes per partition.
    #
    # Topology mirrors the real patient 000481858468:
    #   19 sources (3 empty, 16 with varying text sizes, 2 near the cap)
    #   76 aggregated ResolvedCode objects (one code per source pair)
    from libs.sbar.source_resolver import ResolvedCode

    # 3 empty sources (e.g. un-chunked DocumentReferences)
    empty = [
        ResolvedSource(
            source_label="DocumentReference",
            source_id=f"dr-{i}",
            text=None,
            codes=[],
            metadata={},
        )
        for i in range(3)
    ]
    # 14 small-medium sources
    mid = [
        ResolvedSource(
            source_label="Chunk",
            source_id=f"chunk-{i}",
            text="x" * (200 + i * 100),
            codes=[],
            metadata={},
        )
        for i in range(14)
    ]
    # 2 large sources near the per-source cap
    large = [
        ResolvedSource(
            source_label="Chunk",
            source_id="chunk-large-a",
            text="x" * 38778,
            codes=[],
            metadata={},
        ),
        ResolvedSource(
            source_label="Chunk",
            source_id="chunk-large-b",
            text="x" * 7660,
            codes=[],
            metadata={},
        ),
    ]
    sources = empty + mid + large

    # 76 codes with realistic evidence text (~1000 chars per sentence),
    # which matches the real patient where codes block = 259k chars =
    # ~72k tokens -- well above the 60k budget ceiling.
    long_evidence = "x" * 1000  # matches real ~1007-char evidence_sentence
    codes = [
        ResolvedCode(
            concept_id=f"1234{i:04d}000",
            term=f"Clinical finding {i}",
            semantic_tag="finding",
            assertion="present",
            evidence=f"Clinical evidence snippet {i}",
            evidence_sentence=long_evidence,
            source_id=f"chunk-{i % 14}",
            source_label="Chunk",
        )
        for i in range(76)
    ]

    parts, report = partition_background_sources(
        sources,
        codes,
        referring_specialty="gynaecology",
        max_input_tokens=60000,
    )

    assert report.too_many_parts is False, (
        f"Partitioner refused 19 sources + 76 codes at 60k token budget. "
        f"The codes overhead should not block packing (total_records={report.total_records})"
    )
    assert len(parts) >= 1
    # Every source_id must appear in at least one partition.
    seen = {d.source_id for p in parts for d in p.descriptors}
    all_ids = {s.source_id for s in sources}
    assert seen == all_ids, f"Missing from partitions: {all_ids - seen}"


def test_partitioner_splits_when_code_evidence_exceeds_part_budget() -> None:
    """Fat code evidence must split parts, not one oversized prompt.

    Live gynae 2WW packs (17 sources, 300+ codes, ~1000-char
    evidence_sentence) serialise to ~260k tokens. The packer used to
    ignore codes, send one part, and Azure rejected it as
    context_length_exceeded.
    """
    sources = [
        ResolvedSource(
            source_label="Chunk",
            source_id=f"chunk-{i}",
            text="finding",
            codes=[],
            metadata={},
        )
        for i in range(17)
    ]
    long_evidence = "x" * 1000
    codes = [
        ResolvedCode(
            concept_id=f"1234{i:04d}000",
            term=f"Clinical finding {i}",
            semantic_tag="finding",
            assertion="present",
            evidence=long_evidence,
            evidence_sentence=long_evidence,
            source_id=f"chunk-{i % 17}",
            source_label="Chunk",
        )
        for i in range(358)
    ]
    budget = 60000
    parts, report = partition_background_sources(
        sources,
        codes,
        referring_specialty="gynaecology",
        max_input_tokens=budget,
    )

    assert report.too_many_parts is False
    assert len(parts) >= 2
    seen = {d.source_id for p in parts for d in p.descriptors}
    assert seen == {f"chunk-{i}" for i in range(17)}
    for part in parts:
        assert _estimate_tokens(part.user_message) <= budget
        assert part.estimated_input_tokens <= budget


def test_partitioner_accepts_17_large_sources_with_default_max_parts() -> None:
    # Regression: a complex referral with 17 resolved sources each near
    # the per-source char cap (a multi-comorbidity patient with dense lab
    # results) must not be refused. The old default ceiling of 8 parts
    # was too low; 12 is the new minimum ceiling.
    #
    # At 60k input tokens and 4000-char cap each source serialises to
    # ~1111 tokens. 17 sources = ~18900 tokens. With the 4000-token
    # system reserve that leaves ~56k per part budget; at 2 sources per
    # part that requires ~9 parts -- over the old limit of 8.
    sources = [_make_source(i, text_len=4000) for i in range(17)]
    parts, report = partition_background_sources(
        sources,
        [],
        referring_specialty="gynaecology",
        max_input_tokens=12000,  # tight budget forces multi-part packing
    )
    assert report.too_many_parts is False, (
        f"Expected 17 large sources to fit within the default max_parts "
        f"ceiling but partitioner refused (total_records={report.total_records})"
    )
    assert len(parts) >= 1
    seen = {d.source_id for p in parts for d in p.descriptors}
    assert seen == {f"enc-{i}" for i in range(17)}


def test_partitioner_refuses_when_too_many_parts_needed() -> None:
    # 50 large sources with a tiny budget would need many more than
    # max_parts partitions. The partitioner must refuse cleanly so
    # the caller can return a friendly "pick fewer records" error.
    sources = [_make_source(i, text_len=4000) for i in range(50)]

    parts, report = partition_background_sources(
        sources,
        [],
        referring_specialty=None,
        max_input_tokens=2000,
        system_prompt_reserve_tokens=1000,
        max_parts=4,
    )

    assert parts == []
    assert report.too_many_parts is True
    assert report.total_records == 50


def test_partitioner_user_message_is_valid_json_in_code_fence() -> None:
    sources = [_make_source(i, text_len=300) for i in range(2)]
    parts, _ = partition_background_sources(
        sources, [], referring_specialty="cardiology", max_input_tokens=60000
    )

    msg = parts[0].user_message
    # Same envelope as the legacy single-call Background user message:
    #   "CONTEXT:\n```json\n<body>\n```"
    match = re.search(r"```json\n(?P<body>.*)\n```", msg, re.DOTALL)
    assert match
    body = json.loads(match.group("body"))
    assert body["referring_specialty"] == "cardiology"
    assert {s["id"] for s in body["sources"]} == {"enc-0", "enc-1"}


def test_partitioner_no_record_dropped_invariant_under_record_split() -> None:
    # Mix of small records and one giant one. Even after intra-record
    # splitting, every original source_id must appear at least once.
    small = [_make_source(i, text_len=200) for i in range(5)]
    big = ResolvedSource(
        source_label="Document",
        source_id="doc-huge",
        text="z" * 40000,
        codes=[],
        metadata={},
    )
    parts, report = partition_background_sources(
        small + [big],
        [],
        referring_specialty=None,
        max_input_tokens=4000,
        system_prompt_reserve_tokens=1000,
    )

    assert report.too_many_parts is False
    seen = _all_source_ids_in_partitions(parts)
    assert seen == {f"enc-{i}" for i in range(5)} | {"doc-huge"}
