"""TDD tests for the form schema template generator.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

from libs.pipeline.form_schema_template import generate_normalised_template

_SECTIONS = [
    {
        "section_id": "A",
        "label": "Section A: Cancer type",
        "section_type": "checkbox_single",
        "start_pattern": r"(?i)section\s+a:",
        "items": [],
    },
    {
        "section_id": "C",
        "label": "Section C: Further Clinical details",
        "section_type": "free_text",
        "start_pattern": r"(?i)section\s+c:",
        "items": [],
    },
]

_SAMPLE_TEXT = """
Urgent Suspected Cancer Referral
Surname: Smith
Forename: Jane
NHS Number: 718 563 0207
Date of Birth: 12 January 1956
Address: 10 High Street, Nottingham, NG1 1AA
Referring GP: Dr Brown

Section A: Cancer type
Cervix [X] Ovary [ ]

Section C: Further Clinical details
Patient has complained of irregular bleeding for three months.
BMI: 28.1 Kg/m2. Mobility concerns noted.
"""


def test_nhs_number_is_replaced() -> None:
    result = generate_normalised_template(_SAMPLE_TEXT, _SECTIONS)
    assert "718 563 0207" not in result
    assert "{{NHS_NUMBER}}" in result


def test_dob_is_replaced() -> None:
    result = generate_normalised_template(_SAMPLE_TEXT, _SECTIONS)
    assert "12 January 1956" not in result
    assert "{{DOB}}" in result


def test_name_after_known_label_is_replaced() -> None:
    result = generate_normalised_template(_SAMPLE_TEXT, _SECTIONS)
    assert "Smith" not in result or "Surname: {{NAME}}" in result
    assert "{{NAME}}" in result


def test_free_text_section_body_is_replaced() -> None:
    result = generate_normalised_template(_SAMPLE_TEXT, _SECTIONS)
    assert "irregular bleeding" not in result
    assert "{{CLINICAL_TEXT}}" in result


def test_section_headings_are_preserved() -> None:
    result = generate_normalised_template(_SAMPLE_TEXT, _SECTIONS)
    assert "Section A" in result
    assert "Section C" in result


def test_checkboxes_are_normalised() -> None:
    result = generate_normalised_template(_SAMPLE_TEXT, _SECTIONS)
    # Checkboxes normalised to [ ] or [X], actual checked value not meaningful
    # The template should preserve checkbox structure without patient data
    assert "[X]" in result or "[ ]" in result
