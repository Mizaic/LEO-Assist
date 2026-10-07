"""Red tests: attached documents are clinical or administrative.

A GP-practice Generic Referral Cover Sheet (NHS Standard Contract
clause 6.13, Jess's Rule, must not be rejected) is administrative.
It must not reach the extractor or become the SBAR headline.

A Clinical Information.pdf that carries presenting complaint stays
clinical. Classification is by title and body, not by file type.

Atlas trace:
  DI: DI-C2C1E3E8
  DO: DO-BB31F9A5
  VT: VT-6FE171F8
  Risk: R-07FC04CB

"""

from __future__ import annotations

from unittest.mock import patch

from libs.ner.form_layout_rules import NON_EXTRACTABLE_MARKER, llm_facing_text
from libs.pipeline.document_role import (
    classify_document_role,
    clinical_letter_text,
    seal_administrative_documents,
)
from libs.sbar.situation_source import build_structured_situation

_COVER_SHEET = (
    "--- Document: Generic Referral Cover Sheet.doc ---\n\n"
    "NHS Standard Contract clause 6.13\n"
    "This referral must not be rejected.\n"
    "Jess's Rule: if a patient or family raises a concern, listen.\n"
)

_GP_FORM = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n\n"
    "Section A: cancer type suspected\n"
    "Cervix [X] Ovary [ ]\n"
    "Postmenopausal bleeding for 6 weeks\n"
)

_CLINICAL_PDF = (
    "--- Document: Clinical Information.pdf ---\n\n"
    "NHS Confidential\n"
    "Clinical Information Summary\n"
    "Reason for referral\n"
    "Patchy erythematous rash on the lower part of the left breast.\n"
)

_ADMIN_PHRASES = (
    "must not be rejected",
    "Jess's Rule",
    "clause 6.13",
)


def test_cover_sheet_title_is_administrative() -> None:
    role = classify_document_role(
        "Generic Referral Cover Sheet.doc",
        "NHS Standard Contract clause 6.13",
    )
    assert role == "administrative"


def test_two_week_wait_form_is_clinical() -> None:
    role = classify_document_role(
        "23 Jun 2026 Two Week Wait Referral to Gynaecology .doc",
        "Section A: cancer type suspected\nCervix [X]",
    )
    assert role == "clinical"


def test_clinical_information_pdf_with_narrative_is_clinical() -> None:
    role = classify_document_role(
        "Clinical Information.pdf",
        "Reason for referral\nPatchy erythematous rash on the left breast.",
    )
    assert role == "clinical"


def test_seal_marks_every_cover_sheet_line() -> None:
    sealed = seal_administrative_documents(_COVER_SHEET)
    lines = [ln for ln in sealed.splitlines() if ln.strip()]
    unmarked = [ln for ln in lines if not ln.strip().startswith(NON_EXTRACTABLE_MARKER)]
    assert not unmarked, f"Cover sheet lines still extractable: {unmarked}"


def test_seal_leaves_clinical_form_extractable() -> None:
    sealed = seal_administrative_documents(_GP_FORM)
    facing = llm_facing_text(sealed)
    assert "Postmenopausal bleeding" in facing
    assert "Cervix [X]" in facing


def test_llm_facing_text_drops_cover_sheet_from_mixed_bundle() -> None:
    sealed = seal_administrative_documents(_GP_FORM + "\n\n" + _COVER_SHEET)
    facing = llm_facing_text(sealed)
    for phrase in _ADMIN_PHRASES:
        assert phrase not in facing, f"Cover sheet reached the model: {phrase!r}"
    assert "Postmenopausal bleeding" in facing


def test_clinical_letter_text_excludes_cover_sheet() -> None:
    letter = clinical_letter_text(_COVER_SHEET + "\n\n" + _GP_FORM)
    for phrase in _ADMIN_PHRASES:
        assert phrase not in letter
    assert "Postmenopausal bleeding" in letter


def test_sbar_headline_does_not_use_cover_sheet() -> None:
    result = build_structured_situation(
        referral_request=None,
        referral_reason=None,
        trigger_scoped_letter=_COVER_SHEET + "\n\n" + _GP_FORM,
        form_clinical_section="Postmenopausal bleeding for 6 weeks",
    )
    for phrase in _ADMIN_PHRASES:
        assert phrase not in result.headline
    assert "Postmenopausal bleeding" in result.headline


def test_sbar_headline_honest_when_only_cover_sheet() -> None:
    result = build_structured_situation(
        referral_request=None,
        referral_reason=None,
        trigger_scoped_letter=_COVER_SHEET,
    )
    for phrase in _ADMIN_PHRASES:
        assert phrase not in result.headline
    assert "not documented" in result.headline.lower()


def test_chunk_state_seals_cover_sheet_but_keeps_raw_text() -> None:
    from libs.pipeline.document_chunk_loader import build_document_chunk_state

    rows = [
        {
            "chunk_id": "chunk-0",
            "text": _GP_FORM,
            "ordinal": 0,
            "char_start": None,
            "char_end": None,
        },
        {
            "chunk_id": "chunk-1",
            "text": _COVER_SHEET,
            "ordinal": 1,
            "char_start": None,
            "char_end": None,
        },
    ]
    with patch(
        "libs.pipeline.document_chunk_loader._recognise_chunks",
        return_value=[],
    ):
        state = build_document_chunk_state(rows)
    cover = state["sentences"][1]["text"]
    facing = llm_facing_text(cover)
    for phrase in _ADMIN_PHRASES:
        assert phrase not in facing
        assert phrase in state["encounter_text"]
    assert "Postmenopausal bleeding" in llm_facing_text(state["sentences"][0]["text"])
