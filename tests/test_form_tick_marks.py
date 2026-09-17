"""Bare X / x ticks count the same as [X] / [x].

Converted NHS forms print a tick as [X], [x], X, or x. Completeness
and checkbox seeding must treat all four as ticked.

Atlas:
  DI: DI-5C9CA57B
  DI: DI-50BE367C
  DO: DO-85BBD932
  VT: VT-8426C84D
"""

from __future__ import annotations

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_section_hits import collect_section_hits
from libs.pipeline.form_tick_marks import mark_in_span, yes_no_answer


_GYNAE_A = FormSection(
    section_id="section_a_cancer_type",
    section_type="checkbox_multi",
    label="Section A: Gynaecological Cancer type suspected",
    start_pattern=r"(?i)section\s+a",
    items=[
        FormSchemaItem(pattern="Ovary", entity_text="Suspected ovarian cancer"),
        FormSchemaItem(pattern="Cervix", entity_text="Suspected cervical cancer"),
        FormSchemaItem(
            pattern="Endometrium", entity_text="Suspected endometrial cancer"
        ),
        FormSchemaItem(pattern="Vagina", entity_text="Suspected vaginal cancer"),
        FormSchemaItem(pattern="Vulva", entity_text="Suspected vulval cancer"),
    ],
)

_GYNAE_B = FormSection(
    section_id="section_b_symptoms",
    section_type="checkbox_yesno",
    label="Section B: Signs/symptoms",
    start_pattern=r"(?i)section\s+b",
    items=[
        FormSchemaItem(
            pattern="B4.",
            entity_text="Suspicious pelvic mass on ultrasound",
        ),
        FormSchemaItem(
            pattern="B5.",
            entity_text="Postmenopausal bleeding",
        ),
    ],
)


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="tick-marks",
        fingerprint="tick-marks",
        form_name="Tick marks",
        sections=[_GYNAE_A, _GYNAE_B],
        created_by="test",
    )


def test_bracket_x_upper_and_lower_are_ticked() -> None:
    assert mark_in_span("[X]") is True
    assert mark_in_span("[x]") is True
    assert mark_in_span("[ ]") is False
    assert mark_in_span("[]") is False


def test_bare_x_upper_and_lower_are_ticked() -> None:
    assert mark_in_span(" X ") is True
    assert mark_in_span(" x ") is True
    assert mark_in_span("Endometrium X Vagina") is True


def test_letter_x_inside_a_word_is_not_a_tick() -> None:
    assert mark_in_span(" cervix ") is None
    assert mark_in_span(" Extra ") is None


def test_later_bare_x_does_not_tick_an_earlier_empty_box() -> None:
    assert mark_in_span(" [ ] Cervix [ ] Endometrium X") is False


def test_packed_row_bare_x_marks_only_endometrium() -> None:
    letter = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [ ] Endometrium X Vagina [ ] Vulva [ ]\n"
    )
    hits = collect_section_hits(_schema(), [letter])
    by_item = {h["item_pattern"]: h["checked"] for h in hits}
    assert by_item["Endometrium"] is True
    assert by_item["Ovary"] is False
    assert by_item["Cervix"] is False
    assert by_item["Vagina"] is False
    assert by_item["Vulva"] is False


def test_packed_row_bracket_x_still_marks_cervix() -> None:
    letter = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
    )
    hits = collect_section_hits(_schema(), [letter])
    by_item = {h["item_pattern"]: h["checked"] for h in hits}
    assert by_item["Cervix"] is True
    assert by_item["Endometrium"] is False


def test_yes_bare_x_counts_as_yes() -> None:
    assert yes_no_answer("B4. Suspicious pelvic mass | Yes X No [ ]") == "yes"
    assert yes_no_answer("B5. Postmenopausal bleeding | Yes [ ] No X") == "no"
    assert yes_no_answer("B4. Suspicious pelvic mass | Yes [x] No [ ]") == "yes"
    assert yes_no_answer("B4. Suspicious pelvic mass | Yes [X] No [ ]") == "yes"


def test_section_hits_read_yes_bare_x() -> None:
    letter = (
        "Section B: Signs/symptoms\n"
        "B4. Suspicious pelvic mass on pelvic ultrasound | Yes X No [ ]\n"
        "B5. Postmenopausal bleeding | Yes [ ] No [ ]\n"
    )
    hits = collect_section_hits(_schema(), [letter])
    by_item = {h["item_pattern"]: h["checked"] for h in hits}
    assert by_item["B4."] is True
    assert by_item["B5."] is False
