"""Does a taught test row report a result? Rows the gate used to miss.

The converter writes a result cell as "value, date". When one of the two
is blank the cell becomes "128 g/L," or ", 24 Jun 2025". Blood pressure is
written as a pair, "135 / 87 mmHg". Each of these is a real result, and a
missed result is marked "do not extract", so it never reaches the model.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

import pytest

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)
from libs.pipeline.lab_result_evidence import row_reports_a_result


@pytest.mark.parametrize(
    ("row", "labels"),
    [
        ("| Haemoglobin | 128 g/L, |  |  |", ["Haemoglobin"]),
        ("| Heart Rate: | 72 bpm, |  |  |  |", ["Heart Rate:"]),
        ("| Haemoglobin | , 24 Jun 2025 |  |", ["Haemoglobin"]),
        ("| Blood Pressure | 135 / 87 mmHg, |  |  |", ["Blood Pressure"]),
        ("| Blood Pressure | 120/80 |  |", ["Blood Pressure"]),
    ],
)
def test_a_value_or_date_with_its_partner_blank_reports_a_result(
    row: str, labels: list[str]
) -> None:
    assert row_reports_a_result(row, labels) is True


@pytest.mark.parametrize(
    ("row", "labels"),
    [
        ("| Haemoglobin | , |  |  |", ["Haemoglobin"]),
        ("| Height: |  |  |  |  |", ["Height:"]),
        ("| Haemoglobin | 12, |  |", ["Haemoglobin"]),
        ("| CA 125 | Requested, awaiting result | 2ww Gynae |", ["CA 125"]),
    ],
)
def test_blank_or_bare_cells_still_report_nothing(row: str, labels: list[str]) -> None:
    assert row_reports_a_result(row, labels) is False


def test_an_undated_blood_result_reaches_the_model() -> None:
    section = FormSection(
        section_id="blood_results",
        section_type="ordered_tests",
        label="Blood results",
        start_pattern="Blood results within 12 weeks",
        items=[
            FormSchemaItem(
                pattern="Haemoglobin",
                entity_text="Haemoglobin",
                analytes=[{"label": "Haemoglobin", "snomed_code": ""}],
            ),
            FormSchemaItem(
                pattern="Sodium",
                entity_text="Sodium",
                analytes=[{"label": "Sodium", "snomed_code": ""}],
            ),
        ],
    )
    schema = FormSchema(
        schema_id="undated-bloods",
        fingerprint="undated-bloods",
        form_name="Undated bloods",
        sections=[section],
        created_by="test",
    )
    letter = (
        "| * Blood results within 12 weeks are required |\n"
        "| Haemoglobin | 128 g/L, |  |  |\n"
        "| Sodium | , |  |  |\n"
    )
    lines = {
        line.split("|")[1].strip() if "|" in line else line: line
        for line in str(apply_schema_to_text(letter, schema)).splitlines()
        if "Haemoglobin" in line or "Sodium" in line
    }
    assert NON_EXTRACTABLE_MARKER not in lines["Haemoglobin"]
    assert "128 g/L" in lines["Haemoglobin"]
    assert NON_EXTRACTABLE_MARKER in lines["Sodium"]
