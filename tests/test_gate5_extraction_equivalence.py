"""Gate 5 G5.5 -- extraction window size 1 vs 10 equivalence matrix."""

from __future__ import annotations

import pytest

from libs.pipeline.extraction_window import (
    ChunkRef,
    merge_window_entities,
    plan_extraction_windows,
)


def _entity_key(entity: dict) -> tuple[str, str, str, str]:
    return (
        str(entity.get("concept_id") or entity.get("text") or ""),
        str(entity.get("chunk_id") or ""),
        str(entity.get("sentence_id") or ""),
        str(entity.get("assertion") or "present").lower(),
    )


def _simulate_window_entities(
    windows: list,
    chunk_catalog: dict[str, list[dict]],
) -> list[list[dict]]:
    """Return deterministic per-window entities from the chunk catalog."""
    outputs: list[list[dict]] = []
    for window in windows:
        batch: list[dict] = []
        for chunk_id in window.chunk_ids:
            batch.extend(chunk_catalog.get(chunk_id, []))
        outputs.append(batch)
    return outputs


CHUNK_CATALOG: dict[str, list[dict]] = {
    f"c{i}": [
        {
            "concept_id": f"concept-{i}",
            "text": f"finding-{i}",
            "chunk_id": f"c{i}",
            "sentence_id": f"s{i}",
            "assertion": "present",
        }
    ]
    for i in range(15)
}


@pytest.mark.parametrize("chunk_count", [1, 5, 10, 15, 25])
def test_window_one_vs_ten_merge_same_entity_keys(chunk_count: int) -> None:
    """Merged entity keys are identical for window_size 1 and 10."""
    chunks = [ChunkRef(chunk_id=f"c{i}", text=f"text-{i}") for i in range(chunk_count)]
    windows_one = plan_extraction_windows(chunks, window_size=1, window_overlap=0)
    windows_ten = plan_extraction_windows(chunks, window_size=10, window_overlap=1)

    merged_one = merge_window_entities(
        _simulate_window_entities(windows_one, CHUNK_CATALOG)
    )
    merged_ten = merge_window_entities(
        _simulate_window_entities(windows_ten, CHUNK_CATALOG)
    )

    keys_one = {_entity_key(e) for e in merged_one}
    keys_ten = {_entity_key(e) for e in merged_ten}
    assert keys_one == keys_ten


def test_window_one_produces_more_windows_than_ten_for_large_cohort() -> None:
    chunks = [ChunkRef(chunk_id=f"c{i}", text=f"t{i}") for i in range(25)]
    assert len(plan_extraction_windows(chunks, window_size=1, window_overlap=0)) == 25
    assert len(plan_extraction_windows(chunks, window_size=10, window_overlap=1)) == 3


def test_equivalence_matrix_all_chunk_counts_up_to_25() -> None:
    """Full matrix: every chunk count 1..25 yields matching merge keys."""
    mismatches: list[int] = []
    for count in range(1, 26):
        chunks = [ChunkRef(chunk_id=f"c{i}", text=f"t{i}") for i in range(count)]
        keys_one = {
            _entity_key(e)
            for e in merge_window_entities(
                _simulate_window_entities(
                    plan_extraction_windows(chunks, window_size=1, window_overlap=0),
                    CHUNK_CATALOG,
                )
            )
        }
        keys_ten = {
            _entity_key(e)
            for e in merge_window_entities(
                _simulate_window_entities(
                    plan_extraction_windows(chunks, window_size=10, window_overlap=1),
                    CHUNK_CATALOG,
                )
            )
        }
        if keys_one != keys_ten:
            mismatches.append(count)
    assert mismatches == []
