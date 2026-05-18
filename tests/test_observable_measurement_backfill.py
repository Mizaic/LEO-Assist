from __future__ import annotations

from scripts.backfill_observable_measurements import _build_backfill_item


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
