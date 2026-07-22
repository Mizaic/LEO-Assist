"""Gate 3 A3.2-A3.3 -- evidence fields and safe dedupe."""

from __future__ import annotations

from libs.sbar.source_resolver import ResolvedSource, _coerce_codes, aggregate_codes


def test_coerce_codes_carries_evidence_fields() -> None:
    codes = _coerce_codes(
        [
            {
                "concept_id": "123",
                "term": "Weight loss",
                "assertion": "present",
                "evidence": "weight loss",
                "evidence_sentence": "Reports weight loss for 3 weeks.",
                "evidence_start": 10,
                "evidence_end": 21,
                "sentence_index": 2,
                "chunk_id": "chunk-a",
                "run_id": "run-1",
                "confidence": 0.9,
            }
        ],
        source_label="Chunk",
        source_id="chunk-a",
    )
    assert len(codes) == 1
    code = codes[0]
    assert code.evidence_sentence == "Reports weight loss for 3 weeks."
    assert code.evidence_start == 10
    assert code.evidence_end == 21
    assert code.sentence_index == 2
    assert code.chunk_id == "chunk-a"
    assert code.run_id == "run-1"


def test_dedupe_keeps_distinct_chunks_with_same_sentence_text() -> None:
    raw = [
        {
            "concept_id": "123",
            "term": "Weight loss",
            "assertion": "present",
            "evidence": "weight loss",
            "evidence_sentence": "weight loss",
            "evidence_start": 0,
            "evidence_end": 11,
            "sentence_index": 1,
            "chunk_id": "chunk-a",
        },
        {
            "concept_id": "123",
            "term": "Weight loss",
            "assertion": "present",
            "evidence": "weight loss",
            "evidence_sentence": "weight loss",
            "evidence_start": 0,
            "evidence_end": 11,
            "sentence_index": 1,
            "chunk_id": "chunk-b",
        },
    ]
    codes = _coerce_codes(raw, source_label="Chunk", source_id="chunk-a")
    assert len(codes) == 2


def test_dedupe_collapses_five_codes_from_one_sentence_once() -> None:
    raw = [
        {
            "concept_id": str(i),
            "term": f"Term {i}",
            "assertion": "present",
            "evidence": f"evidence {i}",
            "evidence_sentence": "shared sentence",
            "evidence_start": 5,
            "evidence_end": 20,
            "sentence_index": 4,
            "chunk_id": "chunk-a",
        }
        for i in range(5)
    ]
    sources = [
        ResolvedSource(
            source_label="Chunk",
            source_id="chunk-a",
            codes=_coerce_codes(raw, source_label="Chunk", source_id="chunk-a"),
        )
    ]
    aggregated = aggregate_codes(sources)
    assert len(aggregated) == 5
    span_keys = {
        (c.chunk_id, c.evidence_start, c.evidence_end, c.sentence_index)
        for c in aggregated
    }
    assert len(span_keys) == 1
