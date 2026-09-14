from __future__ import annotations

from scripts.backfill_observable_measurements import (
    APPLY_MEASUREMENT,
    LIST_CANDIDATES,
    _build_backfill_item,
)


def test_build_backfill_item_parses_value_unit_and_range() -> None:
    item = _build_backfill_item(
        {
            "rel_id": "rel-1",
            "encounter_id": "enc-1",
            "concept_id": "1003671000000109",
            "term": "Haemoglobin A1c level",
            "source": "lab_coder_v1",
            "evidence": "Haemoglobin A1c level (X772q) 5.6 % [4 - 5.9]",
        }
    )

    assert item is not None
    assert item.value == "5.6"
    assert item.unit == "%"
    assert item.reference_range == "4 - 5.9"


def test_build_backfill_item_uses_evidence_sentence_when_evidence_is_short() -> None:
    item = _build_backfill_item(
        {
            "rel_id": "rel-2",
            "encounter_id": "enc-1",
            "concept_id": "1003671000000109",
            "term": "Haemoglobin A1c level",
            "source": "lab_coder_v1",
            "evidence": "Haemoglobin A1c level",
            "evidence_sentence": "Haemoglobin A1c level (X772q) 9.3 % [4 - 5.9]",
        }
    )

    assert item is not None
    assert item.value == "9.3"
    assert item.unit == "%"
    assert item.reference_range == "4 - 5.9"


def test_build_backfill_item_keeps_letter_date_from_same_chunk_line() -> None:
    item = _build_backfill_item(
        {
            "rel_id": "rel-3",
            "encounter_id": "chunk-1",
            "concept_id": "1022651000000100",
            "term": "Platelet count",
            "source": "pipeline",
            "evidence": "Plts",
            "evidence_sentence": "| FBC | [DATE] | Hb 150 g/L, Plts 300 10^9/L |",
            "chunk_text": (
                "| FBC | 19 Mar 2026 | Hb 150 g/L, Plts 300 10^9/L |\n"
                "| UE | 18 Mar 2026 | Urea 4.0 |\n"
            ),
            "existing_value": "300",
            "existing_unit": "10^9/L",
        }
    )
    assert item is not None
    assert item.observed_at == "2026-03-19"
    assert item.value == "300"
    assert item.unit == "10^9/L"


def test_build_backfill_item_does_not_take_date_from_another_row() -> None:
    item = _build_backfill_item(
        {
            "rel_id": "rel-4",
            "encounter_id": "chunk-1",
            "concept_id": "1001231000000108",
            "term": "Random glucose",
            "source": "pipeline",
            "evidence": "Random Glucose",
            "chunk_text": (
                "| FBC | 19 Mar 2026 | Hb 150 g/L |\n"
                "| Random Glucose | 5 | Fasting Chol. | 8 |\n"
            ),
            "existing_value": "5",
        }
    )
    assert item is None or item.observed_at is None


def test_candidate_query_reads_chunk_documents() -> None:
    assert "(src:Chunk)-[r:DOCUMENTS]->(s)" in LIST_CANDIDATES
    assert (
        "c.text AS chunk_text" in LIST_CANDIDATES
        or "src.text AS chunk_text" in LIST_CANDIDATES
    )


def test_apply_query_stamps_observed_at_without_overwrite() -> None:
    assert "r.observed_at = coalesce(r.observed_at, $observed_at)" in APPLY_MEASUREMENT
