"""VT for DI-5C9CA57B -- generic form layout on mixed 2WW proformas."""

from __future__ import annotations

from libs.ner.form_checkbox_normalizer import extractable_clinical_lines

GYNAE_SNIPPET = """
Section A: Gynaecological Cancer type suspected
(Please put a X in appropriate boxes)
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]
Please take a Ca125 by the time of referral for anyone suspected of Ovarian cancer.
Section B: Signs/symptoms for 14-day rule criteria
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
B2. Lesion on clinical examination of the vulva | Yes [ ] No [ ]
Does the patient know? Please ensure the patient is aware of cancer.
Section C: Further Clinical details
Thank you for seeing this lady with: vaginal discharge- 10/7 yellowish in colour
polyp noted around 5 oclock around cervical opening.
Hb , WCC , Plts , MCV , Neut
"""


def _joined() -> str:
    return " ".join(extractable_clinical_lines(GYNAE_SNIPPET)).lower()


def test_inline_mixed_boxes_keep_only_ticked_option() -> None:
    joined = _joined()
    assert "cervix" in joined
    assert "ovary" not in joined
    assert "endometrium" not in joined


def test_instruction_and_empty_lab_chrome_are_non_extractable() -> None:
    joined = _joined()
    assert "please take a ca125" not in joined
    assert "please put a x" not in joined
    assert "hb , wcc" not in joined
    assert "wcc" not in joined


def test_section_c_narrative_stays_extractable() -> None:
    joined = _joined()
    assert "vaginal discharge" in joined
    assert "polyp noted" in joined


def test_admin_does_the_patient_know_is_non_extractable() -> None:
    joined = _joined()
    assert "does the patient know" not in joined


def test_yes_no_row_keeps_ticked_b1_and_drops_unticked_b2() -> None:
    joined = _joined()
    assert "lesion suspicious of cancer of cervix" in joined
    assert "clinical examination of the vulva" not in joined
