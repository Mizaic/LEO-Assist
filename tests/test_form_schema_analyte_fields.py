"""TDD tests for ordered_tests analyte enrichment.

Covers:
  - FormSchemaItem analyte fields roundtrip through the store layer.
  - Template generator expands analytes with {{NUMERIC_VALUE}} {{UNIT}} markers.
  - apply_schema_analyte_codes overrides inferred observable codes.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import json

from libs.pipeline.form_analyte_codes import apply_schema_analyte_codes
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_schema_request import dict_to_item, dict_to_section
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline.form_schema_store import _schema_to_sections_json
from libs.pipeline.form_schema_template import expand_ordered_tests_row

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FBC_ITEM = FormSchemaItem(
    pattern="FBC",
    entity_text="Full blood count",
    semantic_tag="procedure",
    assertion="present",
    procedure_snomed="26604007",
    procedure_display="Full blood count",
    analytes=[
        {"label": "Hb", "snomed_code": "1022280009", "display": "Haemoglobin"},
        {"label": "WCC", "snomed_code": "413892002", "display": "White cell count"},
        {"label": "Plts", "snomed_code": "61928009", "display": "Platelet count"},
    ],
    value_placeholder="{{NUMERIC_VALUE}} {{UNIT}}",
)

BARE_ITEM = FormSchemaItem(
    pattern="LFTs",
    entity_text="Liver function tests",
    semantic_tag="procedure",
    assertion="present",
)

FBC_SECTION = FormSection(
    section_id="S1",
    section_type="ordered_tests",
    label="Blood Tests",
    start_pattern=r"Blood Tests",
    items=[FBC_ITEM, BARE_ITEM],
)

SCHEMA = FormSchema(
    schema_id="test-schema-1",
    fingerprint="fp-test",
    form_name="Test Form",
    sections=[FBC_SECTION],
    created_by="test",
)


# ---------------------------------------------------------------------------
# 1. Roundtrip through store serialisation / deserialisation
# ---------------------------------------------------------------------------


class TestFormSchemaItemRoundtrip:
    def test_analyte_fields_survive_to_dict(self) -> None:
        """FormSchemaItem with analytes serialises all new fields."""
        raw = {
            "pattern": "FBC",
            "entity_text": "Full blood count",
            "semantic_tag": "procedure",
            "assertion": "present",
            "procedure_snomed": "26604007",
            "procedure_display": "Full blood count",
            "analytes": [
                {"label": "Hb", "snomed_code": "1022280009", "display": "Haemoglobin"}
            ],
            "value_placeholder": "{{NUMERIC_VALUE}} {{UNIT}}",
        }
        item = dict_to_item(raw)
        assert item.procedure_snomed == "26604007"
        assert item.procedure_display == "Full blood count"
        assert len(item.analytes) == 1
        assert item.analytes[0]["label"] == "Hb"
        assert item.value_placeholder == "{{NUMERIC_VALUE}} {{UNIT}}"

    def test_backward_compat_missing_analyte_fields(self) -> None:
        """Old items without analyte fields default safely."""
        raw = {
            "pattern": "LFTs",
            "entity_text": "Liver function tests",
            "semantic_tag": "procedure",
            "assertion": "present",
        }
        item = dict_to_item(raw)
        assert item.procedure_snomed == ""
        assert item.procedure_display == ""
        assert item.analytes == []
        assert item.value_placeholder == ""

    def test_sections_json_includes_analytes(self) -> None:
        """_schema_to_sections_json writes analyte fields to JSON."""
        json_str = _schema_to_sections_json(SCHEMA)
        data = json.loads(json_str)
        fbc_items = data[0]["items"]
        fbc = next(i for i in fbc_items if i["pattern"] == "FBC")
        assert fbc["procedure_snomed"] == "26604007"
        assert len(fbc["analytes"]) == 3
        assert fbc["value_placeholder"] == "{{NUMERIC_VALUE}} {{UNIT}}"

    def test_sections_json_bare_item_defaults(self) -> None:
        """Bare items round-trip with empty analyte defaults."""
        json_str = _schema_to_sections_json(SCHEMA)
        data = json.loads(json_str)
        fbc_items = data[0]["items"]
        lft = next(i for i in fbc_items if i["pattern"] == "LFTs")
        assert lft["procedure_snomed"] == ""
        assert lft["analytes"] == []

    def test_dict_to_section_preserves_analytes(self) -> None:
        """_dict_to_section round-trips analyte data."""
        raw_section = {
            "section_id": "S1",
            "section_type": "ordered_tests",
            "label": "Blood Tests",
            "start_pattern": "Blood Tests",
            "items": [
                {
                    "pattern": "FBC",
                    "entity_text": "Full blood count",
                    "semantic_tag": "procedure",
                    "assertion": "present",
                    "procedure_snomed": "26604007",
                    "procedure_display": "Full blood count",
                    "analytes": [
                        {
                            "label": "Hb",
                            "snomed_code": "1022280009",
                            "display": "Haemoglobin",
                        }
                    ],
                    "value_placeholder": "{{NUMERIC_VALUE}} {{UNIT}}",
                }
            ],
        }
        section = dict_to_section(raw_section)
        assert section.items[0].analytes[0]["label"] == "Hb"


# ---------------------------------------------------------------------------
# 2. Template generator -- expand_ordered_tests_row
# ---------------------------------------------------------------------------


class TestExpandOrderedTestsRow:
    def test_expands_analytes_with_placeholders(self) -> None:
        """expand_ordered_tests_row produces label + placeholder per analyte."""
        result = expand_ordered_tests_row(FBC_ITEM)
        assert "Hb {{NUMERIC_VALUE}} {{UNIT}}" in result
        assert "WCC {{NUMERIC_VALUE}} {{UNIT}}" in result
        assert "Plts {{NUMERIC_VALUE}} {{UNIT}}" in result

    def test_row_contains_battery_label(self) -> None:
        """Battery label appears at the start of the expanded row."""
        result = expand_ordered_tests_row(FBC_ITEM)
        assert result.startswith("FBC")

    def test_bare_item_no_analytes(self) -> None:
        """Items with no analytes return the entity_text unchanged."""
        result = expand_ordered_tests_row(BARE_ITEM)
        assert result == "Liver function tests"

    def test_custom_placeholder(self) -> None:
        """value_placeholder is respected when set."""
        item = FormSchemaItem(
            pattern="eGFR",
            entity_text="eGFR",
            semantic_tag="procedure",
            assertion="present",
            analytes=[{"label": "eGFR", "snomed_code": "80274001", "display": "eGFR"}],
            value_placeholder="{{VALUE}} mL/min",
        )
        result = expand_ordered_tests_row(item)
        assert "{{VALUE}} mL/min" in result


# ---------------------------------------------------------------------------
# 3. apply_schema_analyte_codes
# ---------------------------------------------------------------------------


class TestApplySchemaAnalyteCodes:
    def _make_entity(self, label: str, snomed: str) -> dict:
        return {
            "label": label,
            "snomed_code": snomed,
            "entity_type": "observable",
        }

    def test_overrides_inferred_code_with_taught_code(self) -> None:
        """Entities in the analyte list get the taught SNOMED code."""
        entities = [
            self._make_entity("Hb", "INFERRED-999"),
            self._make_entity("WCC", "INFERRED-888"),
        ]
        chunk_section_map = [{"chunk_idx": 0, "section_id": "S1"}]
        result = apply_schema_analyte_codes(entities, SCHEMA, chunk_section_map)
        hb = next(e for e in result if e["label"] == "Hb")
        assert hb["snomed_code"] == "1022280009"
        wcc = next(e for e in result if e["label"] == "WCC")
        assert wcc["snomed_code"] == "413892002"

    def test_unlisted_entities_unchanged(self) -> None:
        """Entities not in the analyte list are left alone."""
        entities = [self._make_entity("Ferritin", "INFERRED-777")]
        chunk_section_map = [{"chunk_idx": 0, "section_id": "S1"}]
        result = apply_schema_analyte_codes(entities, SCHEMA, chunk_section_map)
        ferritin = next(e for e in result if e["label"] == "Ferritin")
        assert ferritin["snomed_code"] == "INFERRED-777"

    def test_empty_chunk_section_map_uses_all_ordered_tests_sections(self) -> None:
        """No chunk map -- all ordered_tests sections contribute taught codes."""
        entities = [self._make_entity("Hb", "INFERRED-999")]
        result = apply_schema_analyte_codes(entities, SCHEMA, chunk_section_map=[])
        assert result[0]["snomed_code"] == "1022280009"

    def test_returns_copy_not_mutation(self) -> None:
        """Original entity dicts are not mutated."""
        original_code = "INFERRED-999"
        entities = [self._make_entity("Hb", original_code)]
        chunk_section_map = [{"chunk_idx": 0, "section_id": "S1"}]
        apply_schema_analyte_codes(entities, SCHEMA, chunk_section_map)
        assert entities[0]["snomed_code"] == original_code


# ---------------------------------------------------------------------------
# 4. seed_ordered_tests_entities
# ---------------------------------------------------------------------------


# The printed table as it arrives when no test was resulted.
SHERWOOD_BLANK_BLOOD_TEXT = """\
Blood Results (Last):
FBC | Hb, WCC, Plts, MCV, Neut
UE | Na, K, Urea, Creat, eGFR
LFT | ALT, Alk Phos, Bili, Alb, GGT
"""

# The same table once the laboratory results are reported.
SHERWOOD_BLOOD_TEXT = """\
Blood Results (Last):
FBC | Hb 118 g/L, WCC 7.2 x10^9/L, Plts 250, MCV, Neut
UE | Na 138 mmol/L, K, Urea, Creat, eGFR
LFT | ALT, Alk Phos, Bili, Alb, GGT
"""

SHERWOOD_BLOOD_SCHEMA = FormSchema(
    schema_id="test-sherwood-blood",
    fingerprint="fp-sherwood-blood",
    form_name="Sherwood 2WW Gynaecology",
    created_by="test",
    sections=[
        FormSection(
            section_id="blood",
            section_type="ordered_tests",
            label="Blood Results",
            start_pattern=r"(?i)blood results",
            items=[
                FormSchemaItem(
                    pattern="FBC",
                    entity_text="Full blood count",
                    semantic_tag="procedure",
                    assertion="planned",
                    procedure_snomed="26604007",
                    procedure_display="Full blood count",
                    analytes=[
                        {
                            "label": "Hb",
                            "snomed_code": "1022280009",
                            "display": "Haemoglobin",
                        },
                        {
                            "label": "WCC",
                            "snomed_code": "413892002",
                            "display": "White cell count",
                        },
                        {
                            "label": "MCV",
                            "snomed_code": "1022491000000106",
                            "display": "Mean cell volume",
                        },
                    ],
                ),
                FormSchemaItem(
                    pattern="UE",
                    entity_text="Urea and electrolytes",
                    semantic_tag="procedure",
                    assertion="planned",
                    analytes=[
                        {
                            "label": "Na",
                            "snomed_code": "365761005",
                            "display": "Sodium",
                        },
                    ],
                ),
            ],
        )
    ],
)


class TestSeedOrderedTestsEntities:
    def test_seeds_analytes_when_battery_row_present(self) -> None:
        entities = seed_ordered_tests_entities(
            SHERWOOD_BLOOD_TEXT, SHERWOOD_BLOOD_SCHEMA
        )
        labels = {e["label"] for e in entities}
        assert "Hb" in labels
        assert "WCC" in labels
        assert "Na" in labels

    def test_seeds_battery_procedure_entity(self) -> None:
        entities = seed_ordered_tests_entities(
            SHERWOOD_BLOOD_TEXT, SHERWOOD_BLOOD_SCHEMA
        )
        fbc = next(e for e in entities if e["label"] == "FBC")
        assert fbc["snomed_code"] == "26604007"
        assert fbc["semantic_tag"] == "procedure"

    def test_skips_batteries_not_in_letter(self) -> None:
        """A battery absent from the letter is never seeded.

        The letter must also report a result before the battery it does
        name may be seeded, so the FBC row carries values here.
        """
        text = "Blood Results\nFBC | Hb 118 g/L, WCC 7.2 x10^9/L"
        entities = seed_ordered_tests_entities(text, SHERWOOD_BLOOD_SCHEMA)
        labels = {e["label"] for e in entities}
        assert "UE" not in labels
        assert "Na" not in labels
        assert "Hb" in labels

    def test_skips_batteries_named_but_not_resulted(self) -> None:
        """A battery named with no result at all is never seeded.

        The printed table lists every battery whether or not the test was
        done, so a bare label may not seed a procedure or an analyte.
        """
        text = "Blood Results\nFBC | Hb, WCC"
        entities = seed_ordered_tests_entities(text, SHERWOOD_BLOOD_SCHEMA)
        assert entities == []

    def test_blank_printed_table_seeds_nothing(self) -> None:
        """Every row of the printed table is unresulted -- seed nothing."""
        entities = seed_ordered_tests_entities(
            SHERWOOD_BLANK_BLOOD_TEXT, SHERWOOD_BLOOD_SCHEMA
        )
        assert entities == []

    def test_seeds_only_the_analytes_that_carry_a_value(self) -> None:
        """MCV is taught for FBC but is unresulted on this row."""
        entities = seed_ordered_tests_entities(
            SHERWOOD_BLOOD_TEXT, SHERWOOD_BLOOD_SCHEMA
        )
        labels = {e["label"] for e in entities}
        assert "Hb" in labels
        assert "MCV" not in labels
