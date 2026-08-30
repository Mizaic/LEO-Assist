"""Red tests: taught-form prompt contract is off by default and verbatim only.

Atlas trace:
  DI: DI-9D76A65C
  DO: DO-1E60B1D4
  VT: VT-12EBF8F0
  Risk: R-3B38CA10
"""

from __future__ import annotations

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.referral_quality.form_contract import build_form_contract


def _schema(*, prompt_contract: bool = False) -> FormSchema:
    return FormSchema(
        schema_id="demo",
        fingerprint="demo-v1",
        form_name="Demo",
        created_by="test",
        prompt_contract=prompt_contract,
        sections=[
            FormSection(
                section_id="admin_header",
                section_type="admin",
                label="Breast Unit Referral Form header",
                start_pattern="Breast Unit Referral Form",
            ),
            FormSection(
                section_id="section_a",
                section_type="checkbox_multi",
                label="Section A: 2WW symptoms",
                start_pattern="Section A",
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
                start_pattern="Points to remember",
            ),
        ],
    )


def test_contract_omitted_when_flag_off_or_match_is_unknown() -> None:
    schema = _schema(prompt_contract=False)
    assert build_form_contract(schema, match="exact_hash") == ""
    on = _schema(prompt_contract=True)
    assert build_form_contract(on, match="none") == ""
    assert build_form_contract(on, match="fuzzy") == ""


def test_contract_lists_clinical_sections_verbatim_and_empty() -> None:
    text = build_form_contract(_schema(prompt_contract=True), match="org_service")
    assert "Section A: 2WW symptoms" in text
    assert "words from the letter" in text.lower() or "verbatim" in text.lower()
    assert "empty" in text.lower()
    assert "Points to remember" not in text
    assert "Breast Unit Referral Form header" not in text
