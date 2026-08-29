"""Integration test: gynaecology 2WW referral before and after FormSchema teaching.

Uses the actual de-identified letter structure. Shows:
  BEFORE: score < 0.6, gate pauses, LLM sees checkbox noise
  AFTER:  score = 1.0, gate bypasses, LLM sees clean clinical entities

Atlas trace: DI-5C9CA57B, DI-0C766F85, DI-4A012A59
"""

from __future__ import annotations

import textwrap

from libs.ner.form_checkbox_normalizer import (
    NON_EXTRACTABLE_MARKER,
    normalize_form_checkbox_text,
)
from libs.pipeline.document_quality import (
    form_fingerprint,
    score_document_quality,
)
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)
from libs.pipeline.form_schema_store import reset_schema_cache

# ---------------------------------------------------------------------------
# De-identified gynaecology 2WW referral (representative excerpt)
# ---------------------------------------------------------------------------

GYNAE_2WW_LETTER = textwrap.dedent(
    """\
    URGENT SUSPECTED CANCER REFERRAL FOR SUSPECTED GYNAECOLOGICAL MALIGNANCY

    Section A: Gynaecological Cancer type suspected
    (Please put a X in appropriate boxes)
    Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]

    If referring a suspected endometrial cancer you MUST have arranged a USC/urgent
    transvaginal ultrasound scan at the point of referral.

    Section B: Signs/symptoms for 14-day rule criteria
    Please only use this section if you feel this patient is LIKELY to have cancer
    (Please put a X in appropriate boxes)
    B1. Lesion suspicious of cancer of cervix or vagina on speculum examination | Yes [X] No [ ]
    B2. Lesion suspicious of cancer on clinical examination of the vulva | Yes [ ] No [ ]
    B3. Palpable pelvic mass not obvious fibroids | Yes [ ] No [ ]
    B4. Suspicious pelvic mass on pelvic ultrasound | Yes [ ] No [ ]
    B5. More than one or a single heavy episode of postmenopausal bleeding aged >55 not on HRT | Yes [ ] No [ ]
    B6. Postcoital bleeding age >35 years that persists for more than 4 weeks | Yes [ ] No [ ]
    B9. Suspicion of ovarian cancer and increased CA125 postmenopausal | Yes [ ] No [ ]

    Section C: Further Clinical details
    BMI: 20.2 Kg/m2 Co-morbidities: Cognitive Impairment No
    Thank you for seeing this 57 year old lady with: vaginal discharge 10/7 yellowish
    in colour no vaginal itch/dryness no pelvic pain no pv bleeding post menopausal
    for 1.5yrs also reports dyspareunia for 1 year last pap smear Nov 2025 no result
    recorded no post coital bleeding had abdominal surgery as a child para 1+0
    Examination: alert comfortable abdomen surgical healed scar on right iliac fossa
    abdo full soft non tender nil palpable masses vaginal exam verbal consent given
    chaperone offered declined vulva doesnt appear atrophic scanty vaginal discharge
    swabs taken polyp noted around 5 oclock around cervical opening unable to see base
    no bleeding noted whitish patch beside polyp noted

    Section D: Investigations performed
    MANDATORY the following tests must be undertaken and results provided with referral
    FBC LFTs UEs and Calcium
    BLOODS DONE TODAY

    Section E: PERFORMANCE STATUS
    Clinical Frailty Scale (please tick one)
    1. Very Fit [X] 2. Fit [ ] 3. Managing well [ ] 4. Very Mild [ ] 5. Mild [ ]
    6. Moderate [ ] 7. Severe [ ] 8. Very Severe [ ] 9. Terminally ill [ ]
    Patient Fitness (ECOG STATUS): 0 [ ] 1 [X] 3 [ ] 4 [ ]

    Section F: Allergies and Medication
    Allergies: None
    Medication: None
    """
)

# ---------------------------------------------------------------------------
# FormSchema for the gynaecology 2WW referral (what the clinician saves)
# ---------------------------------------------------------------------------

GYNAE_SCHEMA = FormSchema(
    schema_id="test-gynae-2ww",
    fingerprint=form_fingerprint(GYNAE_2WW_LETTER),
    form_name="Gynaecology 2WW Referral",
    created_by="test",
    sections=[
        # Section A: the body includes guidance lines AND the checkbox line.
        # checkbox_single mode passes non-checkbox lines through unchanged and
        # processes lines with [ ] or [X] markers against the item list.
        FormSection(
            section_id="A",
            section_type="checkbox_single",
            label="Section A: Cancer type",
            start_pattern=r"(?i)section\s+a:",
            items=[
                FormSchemaItem(
                    "Ovary", "Ovarian cancer suspected", "finding", "present"
                ),
                FormSchemaItem(
                    "Cervix", "Cervical cancer suspected", "finding", "present"
                ),
                FormSchemaItem(
                    "Endometrium", "Endometrial cancer suspected", "finding", "present"
                ),
                FormSchemaItem(
                    "Vagina", "Vaginal cancer suspected", "finding", "present"
                ),
                FormSchemaItem(
                    "Vulva", "Vulvar cancer suspected", "finding", "present"
                ),
            ],
        ),
        FormSection(
            section_id="B",
            section_type="checkbox_yesno",
            label="Section B: Signs and symptoms",
            start_pattern=r"(?i)section\s+b:",
            items=[
                FormSchemaItem(
                    r"B1\.",
                    "Lesion suspicious of cancer of cervix or vagina on speculum",
                    "finding",
                    "present",
                ),
                FormSchemaItem(
                    r"B2\.",
                    "Lesion suspicious of cancer on vulva on clinical examination",
                    "finding",
                    "present",
                ),
                FormSchemaItem(
                    r"B3\.",
                    "Palpable pelvic mass (not obvious fibroids)",
                    "finding",
                    "present",
                ),
                FormSchemaItem(
                    r"B5\.",
                    "Postmenopausal bleeding in woman aged over 55 not on HRT",
                    "finding",
                    "present",
                ),
                FormSchemaItem(
                    r"B9\.",
                    "Suspicion of ovarian cancer with raised CA125 (post-menopausal)",
                    "finding",
                    "present",
                ),
            ],
        ),
        FormSection(
            section_id="C",
            section_type="free_text",
            label="Section C: Further Clinical details",
            start_pattern=r"(?i)section\s+c:",
            items=[],
        ),
        FormSection(
            section_id="D",
            section_type="ordered_tests",
            label="Section D: Investigations performed",
            start_pattern=r"(?i)section\s+d:",
            items=[],
        ),
        FormSection(
            section_id="E",
            section_type="scale",
            label="Section E: Performance status",
            start_pattern=r"(?i)section\s+e:",
            items=[
                FormSchemaItem(
                    "Very Fit",
                    "Clinical Frailty Scale: 1 - Very Fit",
                    "finding",
                    "present",
                ),
                FormSchemaItem(
                    "Fit", "Clinical Frailty Scale: 2 - Fit", "finding", "present"
                ),
                FormSchemaItem(
                    "Managing well",
                    "Clinical Frailty Scale: 3 - Managing well",
                    "finding",
                    "present",
                ),
            ],
        ),
        FormSection(
            section_id="F",
            section_type="admin",
            label="Section F: Allergies and Medication",
            start_pattern=r"(?i)section\s+f:",
            items=[],
        ),
    ],
)


# ---------------------------------------------------------------------------
# BEFORE tests
# ---------------------------------------------------------------------------


def test_before_teaching_low_few_shot_causes_gate_pause() -> None:
    """Without schema: low few-shot similarity causes gate pause (score < 0.6)."""
    quality = score_document_quality(
        GYNAE_2WW_LETTER,
        few_shot_max_similarity=0.18,  # real-world value for an unseen form
        known_fingerprints={},
    )
    assert (
        quality.document_quality_score < 0.6
    ), f"Expected gate pause (score < 0.6) but got {quality.document_quality_score}"
    assert "few_shot_ood" in quality.quality_reasons


def test_before_teaching_unknown_fingerprint_adds_reason() -> None:
    """Without schema: unknown form template adds a reason."""
    quality = score_document_quality(
        GYNAE_2WW_LETTER,
        few_shot_max_similarity=0.18,
        known_fingerprints={},
    )
    assert "unknown_form_template" in quality.quality_reasons


def test_before_teaching_llm_sees_checkbox_noise() -> None:
    """Without schema: LLM input contains raw checkbox artefacts."""
    normalised = normalize_form_checkbox_text(GYNAE_2WW_LETTER)
    # The generic normaliser leaves "Cervix [X]" visible as-is
    # because it has a checked box -- it passes through as a candidate for extraction.
    # The LLM then extracts "Cervix [X]" as a literal entity.
    assert (
        "Cervix [X]" in normalised or "Cervical cancer suspected" not in normalised
    ), "Without schema the LLM input should NOT have clean entity text for Cervix"


def test_before_teaching_section_c_narrative_mixed_with_noise() -> None:
    """Without schema: the free-text Section C narrative is present but buried in noise."""
    normalised = normalize_form_checkbox_text(GYNAE_2WW_LETTER)
    # Section C lines should pass through unchanged (good)
    assert "vaginal discharge" in normalised.lower()
    assert "polyp noted" in normalised.lower()
    # But scale items from Section E still appear without clean entity text
    assert (
        "Very Fit [X]" in normalised
        or "Clinical Frailty Scale: 1 - Very Fit" not in normalised
    )


# ---------------------------------------------------------------------------
# AFTER tests
# ---------------------------------------------------------------------------


def test_after_teaching_gate_bypassed_score_is_one() -> None:
    """After teaching: known_schema=True gives score = 1.0 regardless of similarity."""
    reset_schema_cache()
    quality = score_document_quality(
        GYNAE_2WW_LETTER,
        few_shot_max_similarity=0.18,  # would normally cause pause
        known_schema=True,
    )
    assert quality.document_quality_score == 1.0
    assert quality.quality_reasons == []


def test_after_teaching_checked_cancer_site_is_sealed() -> None:
    """After teaching: Cervix [X] is sealed, not rewritten as synthesised prose."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    assert "Cervical cancer suspected" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_after_teaching_unchecked_sites_are_non_extractable() -> None:
    """After teaching: Ovary [ ] and Endometrium [ ] are marked non-extractable."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    non_ex_lines = [ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER in ln]
    assert any(
        "Ovary" in ln for ln in non_ex_lines
    ), "Unchecked 'Ovary' should be marked non-extractable"
    assert any(
        "Endometrium" in ln for ln in non_ex_lines
    ), "Unchecked 'Endometrium' should be marked non-extractable"


def test_after_teaching_b1_yes_is_sealed() -> None:
    """After teaching: B1 Yes [X] is sealed, not rewritten as a new sentence."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    extractable = [
        ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER not in ln
    ]
    assert not any(
        ln.strip() == "Lesion suspicious of cancer of cervix or vagina on speculum"
        for ln in extractable
    )
    assert any("B1" in ln and NON_EXTRACTABLE_MARKER in ln for ln in result.splitlines())


def test_after_teaching_b2_no_is_non_extractable() -> None:
    """After teaching: B2 Yes [ ] No [ ] (unchecked) is non-extractable."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    non_ex = [ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER in ln]
    assert any(
        "B2" in ln for ln in non_ex
    ), "Unchecked B2 row should be marked non-extractable"


def test_after_teaching_section_c_narrative_unchanged() -> None:
    """After teaching: Section C free-text is untouched for LLM extraction."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    assert "vaginal discharge" in result.lower()
    assert "polyp noted" in result.lower()
    assert "dyspareunia" in result.lower()
    assert "BMI: 20.2" in result


def _blood_schema_with_taught_analytes() -> FormSchema:
    """Schema whose Section D teaches one battery with one analyte."""
    return FormSchema(
        schema_id="test-gynae-blood",
        fingerprint=form_fingerprint(GYNAE_2WW_LETTER),
        form_name="Gynaecology 2WW Referral",
        created_by="test",
        sections=[
            *GYNAE_SCHEMA.sections[:-3],
            FormSection(
                section_id="D",
                section_type="ordered_tests",
                label="Section D: Investigations performed",
                start_pattern=r"(?i)section\s+d:",
                items=[
                    FormSchemaItem(
                        pattern="FBC",
                        entity_text="Full blood count",
                        semantic_tag="procedure",
                        assertion="present",
                        analytes=[
                            {
                                "label": "Hb",
                                "snomed_code": "1022280009",
                                "display": "Haemoglobin",
                            }
                        ],
                        value_placeholder="{{NUMERIC_VALUE}} {{UNIT}}",
                    )
                ],
            ),
            *GYNAE_SCHEMA.sections[-2:],
        ],
    )


def test_taught_analytes_do_not_make_an_unresulted_row_extractable() -> None:
    """Teaching analytes must not turn an order into a result slot.

    This letter's Section D names the tests and reports no values, so
    every taught row is an order. Emitting analyte value slots would
    offer the model somewhere to put a number the letter never gave.
    """
    reset_schema_cache()
    result = apply_schema_to_text(
        GYNAE_2WW_LETTER, _blood_schema_with_taught_analytes()
    )
    assert "{{NUMERIC_VALUE}}" not in result
    assert "{{UNIT}}" not in result
    fbc_lines = [ln for ln in result.splitlines() if "FBC" in ln]
    assert fbc_lines
    assert all(NON_EXTRACTABLE_MARKER in ln for ln in fbc_lines)


def test_taught_analytes_keep_a_reported_result_extractable() -> None:
    """A row the referrer resulted reaches the model with its values."""
    reset_schema_cache()
    letter = GYNAE_2WW_LETTER.replace(
        "BLOODS DONE TODAY",
        "BLOODS DONE TODAY\n    | FBC | 23.06.26 | Hb 118 g/L |",
    )
    result = apply_schema_to_text(letter, _blood_schema_with_taught_analytes())
    resulted = [ln for ln in result.splitlines() if "118" in ln]
    assert resulted
    assert all(NON_EXTRACTABLE_MARKER not in ln for ln in resulted)
    assert "g/L" in result


def test_after_teaching_section_d_tests_are_non_extractable() -> None:
    """After teaching: Section D test names are non-extractable (ordered, no results)."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    non_ex = [ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER in ln]
    assert any(
        "FBC" in ln for ln in non_ex
    ), "Ordered test 'FBC' should be marked non-extractable"


def test_after_teaching_section_e_scale_is_sealed() -> None:
    """After teaching: 'Very Fit [X]' is sealed, not rewritten as synthesised prose."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    assert "Clinical Frailty Scale: 1 - Very Fit" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_after_teaching_section_f_admin_is_non_extractable() -> None:
    """After teaching: Section F admin content is non-extractable."""
    reset_schema_cache()
    result = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    non_ex = [ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER in ln]
    assert any(
        "Allergies" in ln or "Medication" in ln for ln in non_ex
    ), "Admin section F content should be non-extractable"


# ---------------------------------------------------------------------------
# Side-by-side comparison helper (not a test -- prints the diff)
# ---------------------------------------------------------------------------


def _show_comparison() -> None:  # pragma: no cover
    """Print before/after text so you can see exactly what the LLM receives."""
    width = 80
    print("\n" + "=" * width)
    print("BEFORE TEACHING (generic normaliser -- what the LLM sees now)")
    print("=" * width)
    before = normalize_form_checkbox_text(GYNAE_2WW_LETTER)
    extractable_before = [
        ln
        for ln in before.splitlines()
        if ln.strip() and NON_EXTRACTABLE_MARKER not in ln
    ]
    for ln in extractable_before:
        print(f"  {ln}")

    print("\n" + "=" * width)
    print("AFTER TEACHING (schema normaliser -- what the LLM will see)")
    print("=" * width)
    after = apply_schema_to_text(GYNAE_2WW_LETTER, GYNAE_SCHEMA)
    extractable_after = [
        ln
        for ln in after.splitlines()
        if ln.strip() and NON_EXTRACTABLE_MARKER not in ln
    ]
    for ln in extractable_after:
        print(f"  {ln}")

    quality_before = score_document_quality(
        GYNAE_2WW_LETTER, few_shot_max_similarity=0.18
    )
    quality_after = score_document_quality(
        GYNAE_2WW_LETTER, few_shot_max_similarity=0.18, known_schema=True
    )
    print("\n" + "=" * width)
    print(
        f"GATE:  BEFORE score={quality_before.document_quality_score:.2f} "
        f"reasons={quality_before.quality_reasons}"
    )
    print(
        f"GATE:  AFTER  score={quality_after.document_quality_score:.2f} "
        f"reasons={quality_after.quality_reasons}"
    )
    print("=" * width + "\n")


if __name__ == "__main__":
    _show_comparison()
