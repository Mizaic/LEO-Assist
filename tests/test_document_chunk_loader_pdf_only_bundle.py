"""A referral bundle must never lose every word to attachment stripping.

Some referrals arrive with only an e-RS "Clinical Information" document.
That document is not a rendering of the GP form -- it is a separate
clinical record carrying presenting complaint, examination findings,
medication and past medical history.

``strip_pdf_attachments`` now has exactly one caller,
``bundle_fingerprint``, because the attachment varies between referrals of
one form and hashing it would stop the taught :FormSchema binding. It no
longer touches ``encounter_text``: extraction reads the whole bundle. These
tests hold both halves of that boundary in place -- the fingerprint keeps
ignoring the attachment, and extraction keeps reading it.

The "never empty" guard inside ``strip_pdf_attachments`` still matters. A
bundle holding nothing but the attachment would otherwise fingerprint the
empty string, and every such referral would collide on one hash.

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
    CHUNK_TEXT_SEPARATOR,
    build_document_chunk_state,
    bundle_trim_deletions,
    strip_pdf_attachments,
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
        "libs.pipeline.document_chunk_loader._resolve_chunk_schema",
        return_value=(None, {}),
    ):
        return build_document_chunk_state(rows)


# ---------------------------------------------------------------------------
# Extraction reads the whole bundle
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# The fingerprint still ignores the attachment
# ---------------------------------------------------------------------------


def test_strip_keeps_text_when_the_bundle_is_only_a_pdf_document() -> None:
    """Fingerprinting an empty string would collide every such referral."""
    result = strip_pdf_attachments(_CLINICAL_INFO_ONLY)
    assert result != ""
    assert "Patchy erythematous rash" in result
    assert "Appendicectomy" in result


def test_strip_still_removes_the_pdf_section_from_a_mixed_bundle() -> None:
    """000481914514 binds a taught schema by exact hash -- do not move it."""
    raw = _GP_FORM + CHUNK_TEXT_SEPARATOR + _CLINICAL_INFO_ONLY
    result = strip_pdf_attachments(raw)
    assert "Section A: cancer type suspected" in result
    assert "Patchy erythematous rash" not in result
    assert "Clinical Information Summary" not in result
