"""Form-teacher gaps found while auditing the real 2WW gynaecology letter.

Two shapes in the letter were not expressible before:

1. Patient-awareness rows put the tick box BEFORE the word, as in
   "[X] Yes [ ] No". The normaliser only understood "Yes [X]", so a
   Yes answer was silently dropped. That row records whether the
   patient knows cancer is suspected, so losing it matters.
2. The blood results table puts two batteries on one row, as in
   "| CRP | | | ESR | |". Only the first battery was expanded, so the
   second battery and all of its analytes were lost.

Atlas trace: DI-5C9CA57B, DI-26546721
"""

from __future__ import annotations

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.blood_panel_presets import blood_panel_preset_payload
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities

AWARENESS_SECTION = FormSection(
    section_id="AW",
    section_type="checkbox_yesno",
    label="Does the patient know?",
    start_pattern=r"(?i)does the patient know",
    items=[
        FormSchemaItem(
            pattern="referred on an urgent basis",
            entity_text="Patient aware of urgent cancer referral",
        ),
        FormSchemaItem(
            pattern="holiday plans in the next 2 months",
            entity_text="Patient has holiday plans in the next two months",
        ),
    ],
)


def _schema(*sections: FormSection) -> FormSchema:
    return FormSchema(
        schema_id="s1",
        fingerprint="fp-sherwood",
        form_name="2WW Gynaecology",
        sections=list(sections),
        created_by="test",
    )


def _preset_section() -> FormSection:
    items = [
        FormSchemaItem(
            pattern=row["pattern"],
            entity_text=row["entity_text"],
            semantic_tag=row["semantic_tag"],
            assertion=row["assertion"],
            procedure_snomed=row["procedure_snomed"],
            procedure_display=row["procedure_display"],
            analytes=row["analytes"],
        )
        for row in blood_panel_preset_payload()
    ]
    return FormSection(
        section_id="BLOODS",
        section_type="ordered_tests",
        label="Blood Results",
        start_pattern=r"(?i)blood results",
        items=items,
        semantic_tags=["procedure", "observable"],
    )


# ---------------------------------------------------------------------------
# Gap 1 -- tick box before the word
# ---------------------------------------------------------------------------


def test_box_before_yes_is_read_as_a_yes_answer() -> None:
    text = (
        "Does the patient know?\n"
        "| Is the patient aware that they have been referred on an urgent "
        "basis? | [X] Yes [ ] No |\n"
    )
    result = apply_schema_to_text(text, _schema(AWARENESS_SECTION))
    assert "Patient aware of urgent cancer referral" in result


def test_box_before_no_is_not_read_as_a_yes_answer() -> None:
    text = (
        "Does the patient know?\n"
        "| Does the patient have any holiday plans in the next 2 months? "
        "| [X] No [ ] Yes |\n"
    )
    result = apply_schema_to_text(text, _schema(AWARENESS_SECTION))
    assert "Patient has holiday plans in the next two months" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_word_before_box_still_works() -> None:
    text = (
        "Does the patient know?\n"
        "| Is the patient aware that they have been referred on an urgent "
        "basis? | Yes [X] No [ ] |\n"
    )
    result = apply_schema_to_text(text, _schema(AWARENESS_SECTION))
    assert "Patient aware of urgent cancer referral" in result


def test_no_answered_before_the_box_is_not_a_yes() -> None:
    text = (
        "Does the patient know?\n"
        "| Is the patient aware that they have been referred on an urgent "
        "basis? | No [X] Yes [ ] |\n"
    )
    result = apply_schema_to_text(text, _schema(AWARENESS_SECTION))
    assert "Patient aware of urgent cancer referral" not in result


def test_unanswered_row_stays_non_extractable() -> None:
    text = (
        "Does the patient know?\n"
        "| New presentation with PMB | Yes [ ] |\n"
        "| Is the patient aware that they have been referred on an urgent "
        "basis? | [ ] Yes [ ] No |\n"
    )
    result = apply_schema_to_text(text, _schema(AWARENESS_SECTION))
    assert "Patient aware of urgent cancer referral" not in result


# ---------------------------------------------------------------------------
# Gap 2 -- two batteries on one blood results row
# ---------------------------------------------------------------------------


def test_crp_and_esr_on_one_row_both_expand() -> None:
    text = "Blood Results (Last ):\n| CRP |  |  | ESR |  |\n"
    result = apply_schema_to_text(text, _schema(_preset_section()))
    assert "CRP |" in result
    assert "ESR |" in result


def test_tfts_and_inr_on_one_row_both_expand() -> None:
    text = "Blood Results (Last ):\n| TFTs |  | TSH , Free T4 | INR |  |\n"
    result = apply_schema_to_text(text, _schema(_preset_section()))
    assert "TSH" in result
    assert "Free T4" in result
    assert "INR" in result


def test_single_battery_row_is_unchanged_in_shape() -> None:
    """One row in, one row out -- and unresulted, so nothing to extract."""
    text = "Blood Results (Last ):\n| FBC |  | Hb , WCC , Plts , MCV , Neut |  |\n"
    result = apply_schema_to_text(text, _schema(_preset_section()))
    body = [ln for ln in result.splitlines() if "FBC" in ln]
    assert len(body) == 1
    assert "Hb" in body[0]
    assert NON_EXTRACTABLE_MARKER in body[0]


def test_resulted_single_battery_row_stays_extractable() -> None:
    """The same row, once resulted, reaches the model with its values."""
    text = "Blood Results (Last ):\n| FBC | 23.06.26 | Hb 118 g/L |  |\n"
    result = apply_schema_to_text(text, _schema(_preset_section()))
    body = [ln for ln in result.splitlines() if "FBC" in ln]
    assert len(body) == 1
    assert "118" in body[0]
    assert NON_EXTRACTABLE_MARKER not in body[0]


def test_untaught_row_is_still_marked_non_extractable() -> None:
    text = "Blood Results (Last ):\n| Date specimen collected | Battery Headers |\n"
    result = apply_schema_to_text(text, _schema(_preset_section()))
    assert NON_EXTRACTABLE_MARKER in result


def test_seeding_covers_both_batteries_on_a_shared_row() -> None:
    """Both resulted batteries on one row are seeded, not just the first."""
    text = "Blood Results (Last ):\n| CRP | 4 mg/L |  | ESR | 12 mm/hr |\n"
    seeded = seed_ordered_tests_entities(text, _schema(_preset_section()))
    labels = {e["label"] for e in seeded}
    assert {"CRP", "ESR"} <= labels


def test_seeding_skips_a_shared_row_with_no_results() -> None:
    """The printed row names both batteries but reports neither result."""
    text = "Blood Results (Last ):\n| CRP |  |  | ESR |  |\n"
    seeded = seed_ordered_tests_entities(text, _schema(_preset_section()))
    assert seeded == []
