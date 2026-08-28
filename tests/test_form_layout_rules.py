"""VT for DI-5C9CA57B -- generic form layout on mixed 2WW proformas."""

from __future__ import annotations

from libs.ner.form_checkbox_normalizer import extractable_clinical_lines
from libs.ner.form_layout_rules import NON_EXTRACTABLE_MARKER, llm_facing_text

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


def test_inline_yes_no_label_dropped_when_no_is_ticked() -> None:
    text = (
        "BMI: 20.2 Kg/m2 Co-morbidities including mobility concerns: "
        "Cognitive Impairment - Yes [ ] No [X]"
    )
    joined = " ".join(extractable_clinical_lines(text)).lower()
    assert "cognitive impairment" not in joined
    assert "20.2" in joined


def test_inline_yes_no_label_kept_when_yes_is_ticked() -> None:
    text = "Cognitive Impairment - Yes [X] No [ ]"
    joined = " ".join(extractable_clinical_lines(text)).lower()
    assert "cognitive impairment" in joined


def test_clinical_context_line_is_non_extractable() -> None:
    text = (
        "Clinical Context: 2WW/2WW Gynaecology\n"
        "Yellow vaginal discharge noted for 10 days"
    )
    joined = " ".join(extractable_clinical_lines(text)).lower()
    assert "clinical context" not in joined
    assert "2ww/2ww" not in joined
    assert "vaginal discharge" in joined


def test_current_repeat_templates_are_non_extractable() -> None:
    text = "Current repeat templates\n" "Metformin 500 mg twice daily\n"
    joined = " ".join(extractable_clinical_lines(text)).lower()
    assert "current repeat templates" not in joined
    assert "metformin" in joined


def test_ecog_instruction_chrome_is_stripped_ticked_grade_kept() -> None:
    text = (
        "| Patient Fitness (ECOG STATUS) : No ECOG in patient record - "
        "consider using tool on 2WW F12 template 0 [ ] 1 [X] 3 [ ] 4 [ ] |"
    )
    joined = " ".join(extractable_clinical_lines(text)).lower()
    assert "no ecog in patient record" not in joined
    assert "consider using tool" not in joined
    assert "1 [x]" in joined or "1[x]" in joined.replace(" ", "")


def test_llm_facing_text_drops_marked_chrome_keeps_clinical() -> None:
    text = (
        f"{NON_EXTRACTABLE_MARKER} Clinical Context: 2WW/2WW Gynaecology\n"
        "Yellow vaginal discharge noted"
    )
    facing = llm_facing_text(text)
    assert "Clinical Context" not in facing
    assert "vaginal discharge" in facing
