"""Red tests: no persisted fact may trace to sealed or unclaimed text.

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
  Risk: R-238CAF49
"""

from __future__ import annotations

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.referral_quality.contamination import find_contaminated_facts

_LETTER = (
    "GP cover: Jess's Rule must not be rejected.\n"
    "Section A: 2WW symptoms\n"
    "A1. Newly presenting discrete hard breast lump | Yes [X]\n"
    "Points to remember:\n"
    "high BMI is a risk factor. Check CA125.\n"
)


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="demo",
        fingerprint="demo-v1",
        form_name="Demo",
        created_by="test",
        sections=[
            FormSection(
                section_id="section_a",
                section_type="checkbox_multi",
                label="Section A",
                start_pattern=r"(?i)section\s+a",
                items=[
                    FormSchemaItem(
                        pattern="A1.",
                        entity_text="Newly presenting discrete hard breast lump",
                    )
                ],
            ),
            FormSection(
                section_id="points",
                section_type="template_noise",
                label="Points to remember",
                start_pattern=r"(?i)points to remember",
            ),
        ],
    )


def test_contamination_fails_when_fact_traces_to_forbidden_region() -> None:
    facts = [
        {
            "text": "high BMI is a risk factor",
            "evidence_text": "high BMI is a risk factor. Check CA125.",
            "assertion": "present",
        }
    ]
    hits = find_contaminated_facts(facts, _schema(), _LETTER)
    assert hits
    assert hits[0].region == "template_noise"


def test_clinical_fact_in_claimed_section_is_clean() -> None:
    facts = [
        {
            "text": "Newly presenting discrete hard breast lump",
            "evidence_text": "A1. Newly presenting discrete hard breast lump",
            "assertion": "present",
        }
    ]
    assert find_contaminated_facts(facts, _schema(), _LETTER) == []


def test_unclaimed_cover_sheet_fact_is_contaminated() -> None:
    facts = [
        {
            "text": "Jess's Rule must not be rejected",
            "evidence_text": "Jess's Rule must not be rejected",
            "assertion": "present",
        }
    ]
    hits = find_contaminated_facts(facts, _schema(), _LETTER)
    assert hits
    assert hits[0].region == "unclaimed"
