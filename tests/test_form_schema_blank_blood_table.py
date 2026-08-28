"""A blank printed blood table must not seed any clinical entity.

The Sherwood Forest (org ``RK5``, service ``7980224``) Gynaecology 2WW
form prints an empty blood-results table on every referral. Every result
cell is blank, so the letter carries no result for any of the taught
batteries. Seeding a coded entity from a bare battery label asserts a
test result that does not exist in the letter.

The rule under test: seed only when the row carries evidence of a
result -- a value, a unit-bearing value, or a specimen date in its own
cell. A bare label is never enough, whatever the taught assertion says.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities

FIXTURES = Path(__file__).parent / "fixtures" / "form_schema"
TEMPLATE_FIXTURE = FIXTURES / "sfh_gynae_2ww_template.json"
CHUNKS_FIXTURE = FIXTURES / "sherwood_gynae_2ww_chunks_deid.json"

BLOOD_TABLE_INDEX = 9

# A resulted row from the same form: specimen date in its own cell and
# three analytes carrying values. MCV and Neut are taught but unresulted.
POPULATED_BLOOD_ROW = """\
| Date specimen collected | Battery Headers | Result indicator |
| --- | --- | --- |

Blood Results (Last ):

| FBC | 23.06.26 | Hb 118 g/L , WCC 7.2 x10^9/L , Plts 250 |  |  |
"""

# The same row with a specimen date but no analyte values at all.
DATED_BLOOD_ROW = "| FBC | 23.06.26 |  |  |  |\n"


def _taught_item(raw: dict) -> FormSchemaItem:
    return FormSchemaItem(
        pattern=str(raw.get("pattern") or ""),
        entity_text=str(raw.get("entity_text") or ""),
        semantic_tag=str(raw.get("semantic_tag") or "finding"),
        assertion=str(raw.get("assertion") or "present"),
        procedure_snomed=str(raw.get("procedure_snomed") or ""),
        procedure_display=str(raw.get("procedure_display") or ""),
        analytes=list(raw.get("analytes") or []),
        value_placeholder=str(raw.get("value_placeholder") or ""),
    )


def _taught_schema() -> FormSchema:
    """Build the taught schema from the seeded Sherwood template fixture.

    Only ``ordered_tests`` sections are built, because seeding reads no
    other section type.
    """
    payload = json.loads(TEMPLATE_FIXTURE.read_text(encoding="utf-8"))
    sections = [
        FormSection(
            section_id=str(raw["section_id"]),
            section_type="ordered_tests",
            label=str(raw.get("label") or ""),
            start_pattern=str(raw.get("start_pattern") or ""),
            items=[_taught_item(i) for i in (raw.get("items") or [])],
        )
        for raw in payload["sections"]
        if raw.get("section_type") == "ordered_tests"
    ]
    return FormSchema(
        schema_id="sfh-gynae-2ww",
        fingerprint="e61c4289e199cfb5",
        form_name=str(payload["form_name"]),
        sections=sections,
        created_by="seed",
        organization_id="RK5",
        service_id="7980224",
    )


def _stored_chunks() -> list[str]:
    payload = json.loads(CHUNKS_FIXTURE.read_text(encoding="utf-8"))
    return [str(c["text"]) for c in payload["chunks"]]


def _blank_blood_table() -> str:
    return _stored_chunks()[BLOOD_TABLE_INDEX]


def _absent_schema() -> FormSchema:
    """A taught battery whose rows are marked absent rather than present."""
    return FormSchema(
        schema_id="absent-schema",
        fingerprint="fp-absent",
        form_name="Absent-assertion form",
        created_by="test",
        sections=[
            FormSection(
                section_id="blood",
                section_type="ordered_tests",
                label="Blood Results",
                start_pattern=r"(?i)blood results",
                items=[
                    FormSchemaItem(
                        pattern="TFTs",
                        entity_text="Thyroid function test",
                        semantic_tag="procedure",
                        assertion="absent",
                        procedure_snomed="35650009",
                        analytes=[
                            {
                                "label": "TSH",
                                "snomed_code": "1022791000000101",
                                "display": "Thyroid stimulating hormone",
                            }
                        ],
                    )
                ],
            )
        ],
    )


def test_blank_printed_blood_table_seeds_nothing() -> None:
    """Chunk 9 is the printed blank table -- no entity may be seeded."""
    entities = seed_ordered_tests_entities(_blank_blood_table(), _taught_schema())
    assert entities == []


def test_blank_table_seeds_nothing_for_the_whole_letter() -> None:
    """No taught battery in the full letter carries a result."""
    letter = "\n\n".join(_stored_chunks())
    entities = seed_ordered_tests_entities(letter, _taught_schema())
    assert entities == []


def test_blank_row_makes_no_absent_claim_either() -> None:
    """A taught ``absent`` battery must not claim the test was not done."""
    entities = seed_ordered_tests_entities(_blank_blood_table(), _absent_schema())
    assert entities == []


def test_populated_row_seeds_battery_and_resulted_analytes() -> None:
    """A row with values still seeds the battery and each resulted analyte."""
    entities = seed_ordered_tests_entities(POPULATED_BLOOD_ROW, _taught_schema())
    labels = {str(e["label"]) for e in entities}
    assert {"FBC", "Hb", "WCC", "Plts"} <= labels


def test_populated_row_keeps_taught_codes_and_assertion() -> None:
    """Seeded entities keep the taught SNOMED codes and semantic tags."""
    entities = seed_ordered_tests_entities(POPULATED_BLOOD_ROW, _taught_schema())
    fbc = next(e for e in entities if e["label"] == "FBC")
    assert fbc["snomed_code"] == "26604007"
    assert fbc["semantic_tag"] == "procedure"
    assert fbc["assertion"] == "present"
    hb = next(e for e in entities if e["label"] == "Hb")
    assert hb["snomed_code"] == "1022431000000105"
    assert hb["semantic_tag"] == "observable entity"


def test_populated_row_skips_unresulted_analytes() -> None:
    """MCV and Neut are taught for FBC but carry no value on this row."""
    entities = seed_ordered_tests_entities(POPULATED_BLOOD_ROW, _taught_schema())
    labels = {str(e["label"]) for e in entities}
    assert "MCV" not in labels
    assert "Neut" not in labels


def test_specimen_date_alone_seeds_only_the_battery() -> None:
    """A dated row proves the test was done, not what it measured."""
    entities = seed_ordered_tests_entities(DATED_BLOOD_ROW, _taught_schema())
    labels = {str(e["label"]) for e in entities}
    assert labels == {"FBC"}
