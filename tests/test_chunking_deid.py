"""Tests for the optional de-identification pass on pulled chunks.

Atlas trace:
  VT: VT-3FE08AC5
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-3FE08AC5")

Uses the existing `libs.deid` regex pass. The pull script writes
`chunks_deid.json` from this helper so validation can keep a
de-identified copy on disk without writing to production Neo4j.
"""

from __future__ import annotations

from libs.chunking.validation_bundle import deidentify_chunk_records


def test_deidentify_chunk_records_redacts_nhs_number_and_postcode() -> None:
    records = [
        {
            "chunk_id": "abc",
            "document_reference_id": "dr-1",
            "ordinal": 1,
            "sha256": "deadbeef",
            "text": "NHS 485 777 3456 lives at SW1A 1AA. DOB 14/03/1985.",
            "char_start": 0,
            "char_end": 52,
        }
    ]
    out = deidentify_chunk_records(records)
    assert "[NHS_NO]" in out[0]["text"]
    assert "[POSTCODE]" in out[0]["text"]
    assert "[DATE]" in out[0]["text"]
    assert "485 777 3456" not in out[0]["text"]
    assert "SW1A 1AA" not in out[0]["text"]
    assert "14/03/1985" not in out[0]["text"]


def test_deidentify_chunk_records_does_not_mutate_source() -> None:
    original_text = "NHS 485 777 3456 noted"
    records = [{"text": original_text, "ordinal": 1}]
    deidentify_chunk_records(records)
    assert records[0]["text"] == original_text


def test_deidentify_chunk_records_leaves_clinical_text() -> None:
    records = [{"text": "Hb 120 g/L. Suspected colorectal cancer.", "ordinal": 1}]
    out = deidentify_chunk_records(records)
    assert "colorectal cancer" in out[0]["text"]
    assert "Hb 120" in out[0]["text"]
