"""Shared normaliser for the form recogniser.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
"""

from __future__ import annotations

import pytest

from libs.form_recognition.normalise import BOX_TOKEN, normalise_text, outline
from tests.form_recognition_corpus import document_by_id, flatten


@pytest.mark.parametrize(
    "box",
    ["[X]", "[x]", "[ ]", "[]", "[*]", "[YES]", "[Yes]", "\u2610", "\u2612", "\u2611"],
)
def test_every_box_style_becomes_one_token(box: str) -> None:
    assert normalise_text(f"Ovary {box} Cervix") == f"ovary {BOX_TOKEN} cervix"


def test_ticked_and_blank_forms_normalise_the_same() -> None:
    blank = "| B1. Lesion on speculum examination | Yes [ ] No [ ] |"
    ticked = "| B1. Lesion on speculum examination | Yes [X] No [ ] |"
    assert normalise_text(blank) == normalise_text(ticked)


def test_pipes_markdown_digits_and_punctuation_are_removed() -> None:
    text = "| **Section A:** Cancer type (14-day rule) | --- |\n## Page 2"
    assert normalise_text(text) == "section a cancer type day rule page"


def test_nfkc_and_casefold_apply() -> None:
    assert normalise_text("\uff33ECTION \u2160 STRASSE Stra\u00dfe") == (
        "section i strasse strasse"
    )


def test_bracketed_words_are_not_boxes() -> None:
    text = "local CRG [Northern, Eastern, Western, Southern]"
    assert BOX_TOKEN not in normalise_text(text)


def test_outline_splits_table_cells_and_drops_separators() -> None:
    text = "| Patient Details | Practice Details |\n| --- | --- |\n| Surname: | |"
    assert outline(text) == ["patient details", "practice details", "surname"]


def test_same_form_in_docx_doc_and_rtf_gives_the_same_outline() -> None:
    docx = outline(document_by_id("devon-gynae-docx"))
    assert docx
    assert outline(document_by_id("devon-gynae-doc")) == docx
    assert outline(document_by_id("devon-gynae-rtf")) == docx


def test_flattened_pdf_style_text_gives_the_same_normalised_text() -> None:
    piped = document_by_id("sfh-gynae-synthetic")
    assert normalise_text(flatten(piped)) == normalise_text(piped)
