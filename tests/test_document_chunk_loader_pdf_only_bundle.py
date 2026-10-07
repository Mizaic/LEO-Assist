"""A referral bundle must never lose every word of an attachment.

Some referrals arrive with only an e-RS "Clinical Information" document.
That document is not a rendering of the GP form -- it is a separate
clinical record carrying presenting complaint, examination findings,
medication and past medical history. Extraction reads the whole bundle.

There is no letter hash any more, so nothing strips the attachment for
fingerprinting either. Each document is recognised on its own text
(DI-E21DF9EF).

Production witness (patient graph, read-only):
  000478696630:leo-referral-bundle -- 1 chunk, 3480 chars, one banner
  ("Clinical Information.pdf"). Stripping would leave 0 chars. Runs
  62370205db1d41e99ade7c40414380d1 and eeb7f1ffc2514359bb690ae7b4edfd04
  read that same text before stripping was in force and found 14 and 21
  clinical facts in it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from libs.pipeline.document_chunk_loader import (
    build_document_chunk_state,
    bundle_trim_deletions,
)

# Shape copied from 000478696630:leo-referral-bundle, content paraphrased.
_CLINICAL_INFO_ONLY = (
    "--- Document: Clinical Information.pdf ---\n\n"
    "NHS Confidential\n"
    "Clinical Information Summary\n"
    "Reason for referral\n"
    "Patchy erythematous rash on the lower part of the left breast.\n"
    "Painful and itchy. Clotrimazole and Betnovate have not helped.\n"
    "Past medical history\n"
    "Appendicectomy. Tonsillectomy. Depression NOS.\n"
)

_GP_FORM = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n\n"
    "Section A: cancer type suspected\n"
    "Cervix [X] Ovary [ ]\n"
)


def _rows(*texts: str) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": f"chunk-{index}",
            "text": text,
            "ordinal": index,
            "char_start": None,
            "char_end": None,
        }
        for index, text in enumerate(texts)
    ]


def _build(rows: list[dict[str, Any]]) -> dict[str, Any]:
    with patch(
        "libs.pipeline.document_chunk_loader._recognise_chunks",
        return_value=[],
    ):
        return build_document_chunk_state(rows)


def test_encounter_text_survives_a_clinical_information_only_bundle() -> None:
    state = _build(_rows(_CLINICAL_INFO_ONLY))
    assert state["encounter_text"] != ""
    assert "Patchy erythematous rash" in state["encounter_text"]


def test_source_text_survives_a_clinical_information_only_bundle() -> None:
    """SourceText content is the space span guards read -- it must match."""
    state = _build(_rows(_CLINICAL_INFO_ONLY))
    assert state["source_text"].content == state["encounter_text"]
    assert "Appendicectomy" in state["source_text"].content


def test_mixed_bundle_keeps_both_documents_for_extraction() -> None:
    """The GP form and the attachment both reach the model and the resolver."""
    state = _build(_rows(_GP_FORM, _CLINICAL_INFO_ONLY))
    encounter_text = state["encounter_text"]
    assert "Section A: cancer type suspected" in encounter_text
    assert "Patchy erythematous rash" in encounter_text
    assert state["source_text"].content == encounter_text


def test_trim_deletions_reproduce_the_encounter_text_for_a_pdf_only_bundle() -> None:
    """The coordinate remap must stay byte-identical to what extraction reads."""
    raw = _CLINICAL_INFO_ONLY
    kept: list[str] = []
    cursor = 0
    for deletion in bundle_trim_deletions(raw):
        kept.append(raw[cursor : deletion.raw_start])
        cursor = deletion.raw_end
    kept.append(raw[cursor:])
    assert "".join(kept) == raw.strip()
