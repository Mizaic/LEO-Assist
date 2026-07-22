"""Gate 3 C3.1-C3.3 -- extraction windows."""

from __future__ import annotations

from libs.pipeline.extraction_window import (
    ChunkRef,
    WindowUsage,
    aggregate_window_usage,
    merge_window_entities,
    plan_extraction_windows,
)


def _chunks(n: int) -> list[ChunkRef]:
    return [ChunkRef(chunk_id=f"c{i}", text=f"text-{i}") for i in range(n)]


def test_planner_creates_three_windows_for_25_chunks() -> None:
    windows = plan_extraction_windows(_chunks(25), window_size=10, window_overlap=1)
    assert len(windows) == 3
    covered = [cid for window in windows for cid in window.chunk_ids]
    assert covered[0] == "c0"
    assert covered[-1] == "c24"
    assert len(set(covered)) == 25


def test_merge_preserves_chunk_provenance() -> None:
    merged = merge_window_entities(
        [
            [
                {
                    "concept_id": "123",
                    "text": "creatinine",
                    "chunk_id": "c1",
                    "sentence_id": "s1",
                    "assertion": "present",
                }
            ],
            [
                {
                    "concept_id": "123",
                    "text": "creatinine",
                    "chunk_id": "c2",
                    "sentence_id": "s9",
                    "assertion": "present",
                }
            ],
        ]
    )
    assert len(merged) == 2


def test_usage_aggregate_equals_sum_of_windows() -> None:
    usages = [
        WindowUsage(window_index=1, input_tokens=100, output_tokens=20, cost_usd=0.01),
        WindowUsage(window_index=2, input_tokens=150, output_tokens=30, cost_usd=0.02),
    ]
    totals = aggregate_window_usage(usages)
    assert totals["input_tokens"] == 250
    assert totals["output_tokens"] == 50
    assert totals["cost_usd"] == 0.03
    assert len(totals["windows"]) == 2
