"""A taught test row whose only analyte has the same label as the row.

A FIT row prints one result, so the form teacher gives the row and its
analyte the same label. The row must still seed both the procedure and
the observable that holds the value; otherwise the value never becomes
a coded observable and the lab-result step cannot read it.

Atlas trace:
  DI: DI-5C9CA57B
  DO: DO-E2F2B277
  VT: VT-1B2063CC
"""

from __future__ import annotations

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline.post_processing import run_post_processing
from libs.pipeline_graph.subgraphs.extraction import _enrich_with_blood_panel_entities

ROW_LABEL = "Faecal Immunochemical test result ug/g"
PROCEDURE_ID = "441579003"
OBSERVABLE_ID = "1049361000000101"

FIT_SCHEMA = FormSchema(
    schema_id="test-fit-row",
    fingerprint="fp-fit-row",
    form_name="Test lower GI form",
    created_by="test",
    sections=[
        FormSection(
            section_id="fit_result",
            section_type="ordered_tests",
            label="Faecal immunochemical test result",
            start_pattern="",
            items=[
                FormSchemaItem(
                    pattern=ROW_LABEL,
                    entity_text="Faecal immunochemical test",
                    semantic_tag="procedure",
                    assertion="present",
                    procedure_snomed=PROCEDURE_ID,
                    procedure_display=(
                        "Measurement of occult blood in stool specimen "
                        "using immunoassay"
                    ),
                    analytes=[
                        {
                            "label": ROW_LABEL,
                            "snomed_code": OBSERVABLE_ID,
                            "display": "Faecal immunochemical test result",
                        }
                    ],
                )
            ],
        )
    ],
)

RESULTED_TEXT = f"Faecal immunochemical test result\n| {ROW_LABEL} > 200 ug/g |  |  |\n"


def _codes(entities):
    return {(e.get("semantic_tag"), e.get("snomed_code")) for e in entities}


def test_row_seeds_the_observable_as_well_as_the_procedure():
    entities = seed_ordered_tests_entities(RESULTED_TEXT, FIT_SCHEMA)
    assert ("procedure", PROCEDURE_ID) in _codes(entities)
    assert ("observable entity", OBSERVABLE_ID) in _codes(entities)


def test_merge_keeps_the_observable_seed_beside_the_procedure_seed():
    result = _enrich_with_blood_panel_entities(
        {"entities": []}, RESULTED_TEXT, [], schema=FIT_SCHEMA
    )
    codes = _codes(result["entities"])
    assert ("procedure", PROCEDURE_ID) in codes
    assert ("observable entity", OBSERVABLE_ID) in codes


def test_post_processing_keeps_the_observable_beside_the_procedure():
    seeds = seed_ordered_tests_entities(RESULTED_TEXT, FIT_SCHEMA)
    codes = _codes(run_post_processing(RESULTED_TEXT, seeds))
    assert ("procedure", PROCEDURE_ID) in codes
    assert ("observable entity", OBSERVABLE_ID) in codes


def test_post_processing_still_drops_a_same_kind_copy():
    seeds = seed_ordered_tests_entities(RESULTED_TEXT, FIT_SCHEMA)
    procedure = next(e for e in seeds if e["semantic_tag"] == "procedure")
    kept = run_post_processing(RESULTED_TEXT, [procedure, dict(procedure)])
    assert len(kept) == 1


def test_an_unresulted_row_still_seeds_nothing():
    text = f"Faecal immunochemical test result\n| {ROW_LABEL} |  |  |\n"
    assert seed_ordered_tests_entities(text, FIT_SCHEMA) == []
