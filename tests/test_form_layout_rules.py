"""VT for DI-5C9CA57B -- generic form layout on mixed 2WW proformas."""

from __future__ import annotations

import json
import re
from pathlib import Path

from libs.ner.form_checkbox_normalizer import extractable_clinical_lines
from libs.ner.form_layout_rules import (
    NON_EXTRACTABLE_MARKER,
    apply_form_layout_rules,
    llm_facing_text,
)

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


# -- Section C prose must survive a checkbox on the same physical line -----
# The Sherwood proforma prints the whole GP narrative on the same line as the
# "Cognitive Impairment" checkbox. Three real orderings seen in production.

SECTION_C_YES_NO_BOTH_BLANK = (
    "| BMI: 29.39 Kg/m2 Co-morbidities including mobility concerns: "
    "Cognitive Impairment - Yes [ ] No [ ] Dear Doctor I am referring "
    "Ms Chris Harris who presented with postmenopausal vaginal bleeding. "
    "She has reported so far two separate episodes. |"
)
SECTION_C_STRAY_X = (
    "| BMI: 19.96 Kg/m2 Co-morbidities including mobility concerns: "
    "Cognitive Impairment - Yes [ ] No x [ ] Consultation. Presenting "
    "Complaint Vulval soreness and presence of sores/blisters for several "
    "months. Uses Vaseline for symptom relief. |"
)
SECTION_C_BOX_BEFORE_LABEL = (
    "| BMI: Co-morbidities including mobility concerns: Cognitive "
    "Impairment - [ ] Yes [X] No Mrs Moore is a 59 years old lady who "
    "presented reporting pv bleeding for approximately 10 days. She is "
    "post-menopausal and on HRT. |"
)


def test_section_c_prose_survives_blank_yes_no_boxes() -> None:
    joined = " ".join(extractable_clinical_lines(SECTION_C_YES_NO_BOTH_BLANK)).lower()
    assert "postmenopausal vaginal bleeding" in joined
    assert "two separate episodes" in joined
    assert "29.39" in joined
    assert "cognitive impairment" not in joined


def test_section_c_prose_survives_stray_x_between_label_and_box() -> None:
    joined = " ".join(extractable_clinical_lines(SECTION_C_STRAY_X)).lower()
    assert "vulval soreness" in joined
    assert "sores/blisters" in joined
    assert "vaseline" in joined
    assert "cognitive impairment" not in joined


def test_section_c_prose_survives_box_before_label_ordering() -> None:
    joined = " ".join(extractable_clinical_lines(SECTION_C_BOX_BEFORE_LABEL)).lower()
    assert "pv bleeding for approximately 10 days" in joined
    assert "on hrt" in joined
    assert "cognitive impairment" not in joined


# -- Box-first Yes/No widgets, as used by most other proformas -------------

BOX_FIRST_BOTH_BLANK = (
    "| [ ] Yes [ ] No Mrs Moore reports pv bleeding for approximately "
    "10 days and is post-menopausal. |"
)
BOX_FIRST_PRINTED_INSTRUCTION = (
    "| [ ] Yes [ ] No If no, please list medication and any repeat " "templates. |"
)
UNTICKED_CRITERION = (
    "| [ ] New unexplained vague abdominal pain for four weeks or more "
    "with no associated change in bowel habit |"
)


def test_box_first_yes_no_keeps_narrative_when_nothing_is_ticked() -> None:
    """Most local proformas print the box before its Yes / No label.

    An untouched widget says nothing about the patient, but the free text
    beside it is the referral reason and has to reach the extractor.
    """
    joined = " ".join(extractable_clinical_lines(BOX_FIRST_BOTH_BLANK)).lower()
    assert "pv bleeding for approximately 10 days" in joined
    assert "post-menopausal" in joined


def test_box_first_yes_no_still_hides_the_printed_instruction() -> None:
    kept = extractable_clinical_lines(BOX_FIRST_PRINTED_INSTRUCTION)
    joined = " ".join(kept).lower()
    assert "please list medication" not in joined
    assert "repeat templates" not in joined


def test_unticked_single_box_criterion_stays_suppressed() -> None:
    """Guard against over-fixing: a lone box labels its own criterion.

    Nothing was ticked, so the printed criterion is not a patient fact.
    """
    joined = " ".join(extractable_clinical_lines(UNTICKED_CRITERION)).lower()
    assert "abdominal pain" not in joined


ECOG_LINE = (
    "| Patient Fitness (ECOG STATUS) : No ECOG in patient record - "
    "consider using tool on 2WW F12 template 0 [ ] 1 [X] 3 [ ] 4 [ ] |"
)

_LOSSLESS_LINES = [
    SECTION_C_YES_NO_BOTH_BLANK,
    SECTION_C_STRAY_X,
    SECTION_C_BOX_BEFORE_LABEL,
    BOX_FIRST_BOTH_BLANK,
    BOX_FIRST_PRINTED_INSTRUCTION,
    UNTICKED_CRITERION,
    ECOG_LINE,
    "| B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ] |",
    "| B2. Lesion on examination of the vulva | Yes [ ] No [ ] |",
    "| Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ] |",
    "| Clinical Context: 2WW/2WW Gynaecology |",
    "| FBC |  | Hb , WCC , Plts , MCV , Neut |  |  |",
]


def _words(text: str) -> set[str]:
    marker = NON_EXTRACTABLE_MARKER.strip("[]")
    return {
        word
        for word in re.findall(r"[A-Za-z0-9.]{3,}", text.lower())
        if word != marker.lower()
    }


def test_layout_rules_only_mark_text_never_delete_it() -> None:
    """Fail-closed: suppression happens by marker, never by deleting text.

    Deleting text inside the normaliser is invisible downstream -- the run
    still completes and simply reports fewer facts. Every rule must keep
    every original word and mark what the extractor should ignore.
    """
    for line in _LOSSLESS_LINES:
        lost = _words(line) - _words(apply_form_layout_rules(line))
        assert not lost, f"layout rules deleted {sorted(lost)} from {line!r}"


# -- Printed guidance is not a patient fact --------------------------------

POINTS_TO_REMEMBER = """Points to remember:

Remember endometrial cancer nearly always occurs in post-menopausal women \
and high BMI is a risk factor.

Think of possible ovarian cancer in a post-menopausal woman with new onset \
bloating, constipation, abdominal pain, urinary symptoms that do not go away \
after 3 weeks (Check CA125 and consider scan as per NICE guidelines)

Do not check CA125 in premenopausal women as it is not a reliable marker of \
ovarian cancer and may result in unnecessary investigations and patient anxiety

Patient summary

| Blood Pressure | 140 / 80 mmHg, 24 Nov 2025 |  |  |
"""


def test_printed_guidance_block_is_not_extractable() -> None:
    joined = " ".join(extractable_clinical_lines(POINTS_TO_REMEMBER)).lower()
    assert "points to remember" not in joined
    assert "endometrial cancer nearly always" not in joined
    assert "think of possible ovarian cancer" not in joined
    assert "do not check ca125" not in joined


def test_guidance_symptom_words_cannot_reach_the_extractor() -> None:
    """The words that became false facts for two real patients."""
    joined = " ".join(extractable_clinical_lines(POINTS_TO_REMEMBER)).lower()
    for word in ("bloating", "constipation", "abdominal pain", "urinary"):
        assert word not in joined, f"{word!r} leaked from printed guidance"


def test_real_observations_beside_guidance_still_extractable() -> None:
    joined = " ".join(extractable_clinical_lines(POINTS_TO_REMEMBER)).lower()
    assert "140 / 80 mmhg" in joined


def test_endometrial_cancer_guidance_alone_is_not_extractable() -> None:
    text = (
        "Remember endometrial cancer nearly always occurs in post-menopausal "
        "women and high BMI is a risk factor."
    )
    assert extractable_clinical_lines(text) == []


# -- Whole-letter guard on the real de-identified referral -----------------

SHERWOOD_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)
# Phrases a clinician would expect to find, and printed text that is not
# about this patient. Both were wrong on the 2026-08-28 production run.
LETTER_MUST_KEEP = (
    "vaginal discharge",
    "polyp noted",
    "dyspareunia",
    "whitish patch",
    "para 1+0",
)
LETTER_MUST_DROP = (
    "endometrial cancer nearly always",
    "think of possible ovarian",
    "do not check ca125",
    "cognitive impairment",
    "no ecog in patient record",
)


def _letter_extractable_text() -> str:
    chunks = json.loads(SHERWOOD_FIXTURE.read_text(encoding="utf-8"))["chunks"]
    return " ".join(
        " ".join(extractable_clinical_lines(str(chunk.get("text") or "")))
        for chunk in chunks
    ).lower()


def test_whole_letter_keeps_every_clinical_phrase() -> None:
    text = _letter_extractable_text()
    missing = [phrase for phrase in LETTER_MUST_KEEP if phrase not in text]
    assert not missing, f"letter lost {missing}"


def test_whole_letter_drops_printed_guidance_and_chrome() -> None:
    text = _letter_extractable_text()
    leaked = [phrase for phrase in LETTER_MUST_DROP if phrase in text]
    assert not leaked, f"non-patient text reached the extractor: {leaked}"


def test_llm_facing_text_drops_marked_chrome_keeps_clinical() -> None:
    text = (
        f"{NON_EXTRACTABLE_MARKER} Clinical Context: 2WW/2WW Gynaecology\n"
        "Yellow vaginal discharge noted"
    )
    facing = llm_facing_text(text)
    assert "Clinical Context" not in facing
    assert "vaginal discharge" in facing
