"""Prefer the 2WW letter over a scan-report Clinical Information line.

Atlas:
  DI: DI-41542A49
  DO: DO-4F133EE7
  VT: VT-95532C93
"""

from __future__ import annotations

from libs.pipeline_graph.referral_reason_chunks import select_reason_chunks


def test_scan_clinical_information_loses_to_reason_for_referral() -> None:
    rows = [
        {
            "chunk_id": "scan",
            "ordinal": 1,
            "text": (
                "US PELVIS: This is a FINAL report. Accession No: RK1 "
                "Clinical Information: constant pain after mirena inserted "
                "3 weeks ago. Typed by: Ahmad Salih (Sonographer)."
            ),
        },
        {
            "chunk_id": "ers",
            "ordinal": 2,
            "text": (
                "Clinical Information Summary\n"
                "Reason for referral\n"
                "2WW See proforma attached"
            ),
        },
        {
            "chunk_id": "letter",
            "ordinal": 3,
            "text": (
                "Section C: Further Clinical details\n"
                "Postmenopausal bleeding on HRT with thickened endometrium."
            ),
        },
    ]

    chosen = select_reason_chunks(rows, limit=3)
    ids = [str(row.get("chunk_id")) for row in chosen]

    assert "scan" not in ids
    assert ids[0] in {"letter", "ers"}
    assert "letter" in ids


def test_generic_clinical_information_used_when_it_is_all_we_have() -> None:
    rows = [
        {
            "chunk_id": "only",
            "ordinal": 1,
            "text": "Clinical information: new left breast lump for 6 weeks.",
        }
    ]

    chosen = select_reason_chunks(rows, limit=3)

    assert [row["chunk_id"] for row in chosen] == ["only"]
