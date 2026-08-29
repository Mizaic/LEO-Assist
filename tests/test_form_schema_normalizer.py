"""TDD tests for form_schema_normalizer (RED phase -- module does not exist yet).

Atlas trace:
  DI: DI-5C9CA57B  (form checkbox normalisation)
"""

from __future__ import annotations

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)

# ---------------------------------------------------------------------------
# Minimal schema fixtures
# ---------------------------------------------------------------------------

CANCER_SITE_SECTION = FormSection(
    section_id="A",
    section_type="checkbox_single",
    label="Section A: Gynaecological Cancer type suspected",
    start_pattern=r"(?i)section\s+a:",
    items=[
        FormSchemaItem(
            pattern="Ovary",
            entity_text="Ovarian cancer suspected",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern="Cervix",
            entity_text="Cervical cancer suspected",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern="Endometrium",
            entity_text="Endometrial cancer suspected",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern="Vagina",
            entity_text="Vaginal cancer suspected",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern="Vulva",
            entity_text="Vulvar cancer suspected",
            semantic_tag="finding",
            assertion="present",
        ),
    ],
)

CRITERIA_SECTION = FormSection(
    section_id="B",
    section_type="checkbox_yesno",
    label="Section B: Signs and symptoms",
    start_pattern=r"(?i)section\s+b:",
    items=[
        FormSchemaItem(
            pattern=r"B1\.",
            entity_text="Lesion suspicious of cancer of cervix or vagina on speculum",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern=r"B2\.",
            entity_text="Lesion suspicious of cancer on clinical examination of vulva",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern=r"B5\.",
            entity_text="Postmenopausal bleeding in woman aged over 55 not on HRT",
            semantic_tag="finding",
            assertion="present",
        ),
    ],
)

NARRATIVE_SECTION = FormSection(
    section_id="C",
    section_type="free_text",
    label="Section C: Further Clinical details",
    start_pattern=r"(?i)section\s+c:",
    items=[],
)

INVESTIGATIONS_SECTION = FormSection(
    section_id="D",
    section_type="ordered_tests",
    label="Section D: Investigations performed",
    start_pattern=r"(?i)section\s+d:",
    items=[],
)

FRAILTY_SECTION = FormSection(
    section_id="E_frailty",
    section_type="scale",
    label="Clinical Frailty Scale",
    start_pattern=r"(?i)clinical frailty scale",
    items=[
        FormSchemaItem(
            pattern="Very Fit",
            entity_text="Clinical Frailty Scale: Very Fit",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern=r"\bFit\b",
            entity_text="Clinical Frailty Scale: Fit",
            semantic_tag="finding",
            assertion="present",
        ),
        FormSchemaItem(
            pattern="Managing well",
            entity_text="Clinical Frailty Scale: Managing well",
            semantic_tag="finding",
            assertion="present",
        ),
    ],
)

ADMIN_SECTION = FormSection(
    section_id="admin_header",
    section_type="admin",
    label="Patient and practice details",
    start_pattern=r"(?i)(patient details|practice details|hospital number)",
    items=[],
)


def _make_schema(*sections: FormSection) -> FormSchema:
    return FormSchema(
        schema_id="test-schema-id",
        fingerprint="abc123",
        form_name="Gynaecology 2WW Referral",
        sections=list(sections),
        created_by="test",
    )


# ---------------------------------------------------------------------------
# checkbox_single tests
# ---------------------------------------------------------------------------


def test_checked_item_does_not_insert_synthesised_text() -> None:
    text = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
    )
    schema = _make_schema(CANCER_SITE_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Cervical cancer suspected" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_unchecked_items_are_non_extractable() -> None:
    text = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
    )
    schema = _make_schema(CANCER_SITE_SECTION)
    result = apply_schema_to_text(text, schema)
    non_ex_lines = [ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER in ln]
    assert any(
        "Ovary" in ln for ln in non_ex_lines
    ), "Unchecked Ovary should be marked non-extractable"
    assert any("Endometrium" in ln for ln in non_ex_lines)


def test_no_checked_item_marks_whole_section_non_extractable() -> None:
    text = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [ ] Endometrium [ ]\n"
    )
    schema = _make_schema(CANCER_SITE_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Ovarian cancer suspected" not in result
    assert "Cervical cancer suspected" not in result


# ---------------------------------------------------------------------------
# checkbox_yesno tests
# ---------------------------------------------------------------------------


def test_yes_checked_does_not_insert_synthesised_text() -> None:
    text = (
        "Section B: Signs and symptoms\n"
        "B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]\n"
    )
    schema = _make_schema(CRITERIA_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Lesion suspicious of cancer of cervix or vagina on speculum" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_no_checked_is_non_extractable() -> None:
    text = (
        "Section B: Signs and symptoms\n"
        "B1. Lesion suspicious of cancer of cervix | Yes [ ] No [X]\n"
    )
    schema = _make_schema(CRITERIA_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Lesion suspicious of cancer of cervix or vagina on speculum" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_unchecked_yesno_row_is_non_extractable() -> None:
    text = (
        "Section B: Signs and symptoms\n"
        "B2. Lesion suspicious on vulva | Yes [ ] No [ ]\n"
    )
    schema = _make_schema(CRITERIA_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Lesion suspicious of cancer on clinical examination" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_multiple_criteria_do_not_insert_synthesised_text() -> None:
    text = (
        "Section B: Signs and symptoms\n"
        "B1. Lesion on cervix | Yes [X] No [ ]\n"
        "B2. Lesion on vulva | Yes [ ] No [X]\n"
        "B5. PMB in woman over 55 | Yes [ ] No [ ]\n"
    )
    schema = _make_schema(CRITERIA_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Lesion suspicious of cancer of cervix or vagina on speculum" not in result
    assert "Lesion suspicious of cancer on clinical examination of vulva" not in result
    assert "Postmenopausal bleeding in woman aged over 55 not on HRT" not in result
    assert result.count(NON_EXTRACTABLE_MARKER) >= 3


# ---------------------------------------------------------------------------
# free_text tests
# ---------------------------------------------------------------------------


def test_free_text_section_is_unchanged() -> None:
    clinical_note = (
        "Section C: Further Clinical details\n"
        "BMI: 20.2 Kg/m2. Vaginal discharge 10/7 yellowish. "
        "Polyp noted around cervical opening.\n"
    )
    schema = _make_schema(NARRATIVE_SECTION)
    result = apply_schema_to_text(clinical_note, schema)
    assert "BMI: 20.2" in result
    assert "Polyp noted" in result
    assert NON_EXTRACTABLE_MARKER not in result


def test_free_text_with_no_checkboxes_passes_through() -> None:
    text = (
        "Section C: Further Clinical details\n"
        "Patient presents with a 3-month history of postmenopausal bleeding.\n"
    )
    schema = _make_schema(NARRATIVE_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "3-month history" in result


# ---------------------------------------------------------------------------
# ordered_tests tests
# ---------------------------------------------------------------------------


def test_ordered_tests_section_is_fully_non_extractable() -> None:
    text = (
        "Section D: Investigations performed\n"
        "MANDATORY tests: FBC, LFTs, UEs and Calcium\n"
        "BLOODS DONE TODAY 23.6.26\n"
    )
    schema = _make_schema(INVESTIGATIONS_SECTION)
    result = apply_schema_to_text(text, schema)
    lines = [ln for ln in result.splitlines() if ln.strip()]
    non_ex_lines = [ln for ln in lines if NON_EXTRACTABLE_MARKER in ln]
    # All non-empty lines (excluding the header) should be non-extractable
    content_lines = [ln for ln in lines if ln.strip() and "Section D" not in ln]
    assert len(non_ex_lines) >= len(content_lines)


def test_ordered_tests_test_names_not_extracted() -> None:
    text = "Section D: Investigations performed\n" "FBC LFTs UEs Calcium\n"
    schema = _make_schema(INVESTIGATIONS_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "FBC" not in result.replace(NON_EXTRACTABLE_MARKER, "").strip() or (
        NON_EXTRACTABLE_MARKER in result
    )


# ---------------------------------------------------------------------------
# scale tests
# ---------------------------------------------------------------------------


def test_scale_checked_value_does_not_insert_synthesised_text() -> None:
    text = (
        "Clinical Frailty Scale\n" "1. Very Fit [X]  2. Fit [ ]  3. Managing well [ ]\n"
    )
    schema = _make_schema(FRAILTY_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "Clinical Frailty Scale: Very Fit" not in result
    assert NON_EXTRACTABLE_MARKER in result


def test_scale_unchecked_items_are_non_extractable() -> None:
    text = (
        "Clinical Frailty Scale\n" "1. Very Fit [X]  2. Fit [ ]  3. Managing well [ ]\n"
    )
    schema = _make_schema(FRAILTY_SECTION)
    result = apply_schema_to_text(text, schema)
    lines_with_marker = [
        ln for ln in result.splitlines() if NON_EXTRACTABLE_MARKER in ln
    ]
    assert any(
        "Fit" in ln or "Managing" in ln for ln in lines_with_marker
    ), "Unchecked scale items should be marked non-extractable"


# ---------------------------------------------------------------------------
# admin tests
# ---------------------------------------------------------------------------


def test_admin_section_is_fully_non_extractable() -> None:
    text = "Patient details\n" "NHS No.: 123456789\n" "Surname: Smith\n"
    schema = _make_schema(ADMIN_SECTION)
    result = apply_schema_to_text(text, schema)
    assert NON_EXTRACTABLE_MARKER in result
    extractable = [
        ln
        for ln in result.splitlines()
        if ln.strip() and NON_EXTRACTABLE_MARKER not in ln
    ]
    assert not any(
        "Smith" in ln for ln in extractable
    ), "Surname (PII) should not appear in extractable lines"


# ---------------------------------------------------------------------------
# multi-section tests
# ---------------------------------------------------------------------------


def test_multi_section_schema_handles_each_section_correctly() -> None:
    text = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [X] Endometrium [ ]\n"
        "Section B: Signs and symptoms\n"
        "B1. Lesion on cervix | Yes [X] No [ ]\n"
        "Section C: Further Clinical details\n"
        "BMI: 20.2 Vaginal discharge noted. Polyp on cervix.\n"
        "Section D: Investigations performed\n"
        "FBC, LFTs, UEs\n"
    )
    schema = _make_schema(
        CANCER_SITE_SECTION,
        CRITERIA_SECTION,
        NARRATIVE_SECTION,
        INVESTIGATIONS_SECTION,
    )
    result = apply_schema_to_text(text, schema)
    assert "Cervical cancer suspected" not in result
    assert "Lesion suspicious of cancer of cervix or vagina on speculum" not in result
    assert "BMI: 20.2" in result
    assert "Polyp on cervix" in result
    non_ex_count = result.count(NON_EXTRACTABLE_MARKER)
    assert non_ex_count >= 2


def test_unmatched_lines_are_not_corrupted() -> None:
    """Lines before the first known section should pass through unchanged."""
    text = (
        "URGENT SUSPECTED CANCER REFERRAL\n"
        "Hospital Number:\n"
        "Section C: Further Clinical details\n"
        "BMI: 20.2\n"
    )
    schema = _make_schema(NARRATIVE_SECTION)
    result = apply_schema_to_text(text, schema)
    assert "BMI: 20.2" in result


def test_empty_text_returns_empty() -> None:
    schema = _make_schema(CANCER_SITE_SECTION)
    assert apply_schema_to_text("", schema) == ""


def test_schema_with_no_sections_returns_text_unchanged() -> None:
    text = "Some text without any known form sections.\n"
    schema = FormSchema(
        schema_id="s",
        fingerprint="fp",
        form_name="Empty",
        sections=[],
        created_by="test",
    )
    result = apply_schema_to_text(text, schema)
    assert result == text


# ---------------------------------------------------------------------------
# semantic_tags -- plural list field
# ---------------------------------------------------------------------------


def test_form_section_has_semantic_tags_list() -> None:
    """FormSection.semantic_tags must be a list of strings."""
    section = FormSection(
        section_id="X",
        section_type="ordered_tests",
        label="Blood Results",
        start_pattern="Blood Results",
        items=[],
        semantic_tags=["procedure", "observable", "finding"],
    )
    assert section.semantic_tags == ["procedure", "observable", "finding"]


def test_form_section_semantic_tags_default_is_list() -> None:
    """FormSection created with no explicit tags defaults to a one-element list."""
    section = FormSection(
        section_id="X",
        section_type="checkbox_yesno",
        label="Criteria",
        start_pattern="Criteria",
        items=[],
    )
    assert isinstance(section.semantic_tags, list)
    assert len(section.semantic_tags) >= 1


def test_form_section_backward_compat_singular_tag() -> None:
    """When loaded from an old record with semantic_tag (singular), it wraps to list."""
    from libs.pipeline.form_schema_store import _dict_to_section

    raw = {
        "section_id": "A",
        "section_type": "checkbox_single",
        "label": "Cancer type",
        "start_pattern": "Cancer type",
        "items": [],
        "semantic_tag": "situation",
    }
    section = _dict_to_section(raw)
    assert section.semantic_tags == ["situation"]


def test_form_section_store_roundtrip_semantic_tags() -> None:
    """semantic_tags list survives a store serialise/deserialise round-trip."""
    from libs.pipeline.form_schema_store import _dict_to_section, _schema_to_sections_json
    import json

    tags = ["procedure", "observable"]
    section = FormSection(
        section_id="B",
        section_type="ordered_tests",
        label="Blood Results",
        start_pattern="Blood Results",
        items=[],
        semantic_tags=tags,
    )
    schema = FormSchema(
        schema_id="s1",
        fingerprint="fp1",
        form_name="Test form",
        sections=[section],
        created_by="test",
    )
    raw_json = _schema_to_sections_json(schema)
    parsed = json.loads(raw_json)
    reloaded = _dict_to_section(parsed[0])
    assert reloaded.semantic_tags == tags


def test_form_section_store_singular_absent_uses_default() -> None:
    """If neither semantic_tags nor semantic_tag is present, default to ['finding']."""
    from libs.pipeline.form_schema_store import _dict_to_section

    raw = {
        "section_id": "C",
        "section_type": "free_text",
        "label": "History",
        "start_pattern": "History",
        "items": [],
    }
    section = _dict_to_section(raw)
    assert section.semantic_tags == ["finding"]
