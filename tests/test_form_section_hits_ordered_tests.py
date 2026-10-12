"""Form-native completeness for taught test tables (ordered_tests).

A test table row counts as filled in exactly when it reports a result,
using the same check that turns the row into facts. A printed but empty
row is a real "not filled in", so the rule can be assessed rather than
degrading the run.

Atlas trace:
  DI: DI-50BE367C
  DO: DO-85BBD932
  VT: VT-8426C84D
  Risk: R-0883B521
"""

from __future__ import annotations

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline.form_section_hits import collect_section_hits

_FIT_HEADING = "Faecal Immunochemical test result ug/g"

_FIT = FormSection(
    section_id="fit_result",
    section_type="ordered_tests",
    label="FIT result",
    start_pattern=_FIT_HEADING,
    items=[
        FormSchemaItem(
            pattern="Faecal Immunochemical",
            entity_text="Faecal immunochemical test",
            analytes=[
                {
                    "label": _FIT_HEADING,
                    "snomed_code": "1049361000000101",
                    "display": "Faecal immunochemical test result",
                }
            ],
        )
    ],
)

_BLOODS = FormSection(
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

_FIT_RESULTED = (
    f"| {_FIT_HEADING} > 200 ug/g, 10 Jun 2026 Date requested: "
    "Date reported (Within 3 months) |  |  |\n"
)
_FIT_EMPTY = f"| {_FIT_HEADING} Date requested: Date reported |  |  |\n"
_BLOODS_EMPTY = (
    "| * Blood results within 12 weeks are required |\n"
    "| Haemoglobin | , |  |  |\n"
    "| Sodium | , |  |  |\n"
)
_BLOODS_RESULTED = (
    "| * Blood results within 12 weeks are required |\n"
    "| Haemoglobin | 128 g/L |  |  |\n"
    "| Sodium | , |  |  |\n"
)


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="ordered-tests-hits",
        fingerprint="ordered-tests-hits",
        form_name="Lower GI test tables",
        sections=[_FIT, _BLOODS],
        created_by="test",
    )


def _hits(letter: str, section_id: str) -> list[dict]:
    return [
        h
        for h in collect_section_hits(_schema(), [letter])
        if h["section_id"] == section_id
    ]


def test_a_resulted_row_on_the_heading_line_counts_as_filled_in() -> None:
    hits = _hits(_FIT_RESULTED, "fit_result")
    assert hits, "the FIT heading line is also its result row"
    assert any(h["checked"] for h in hits)


def test_a_heading_line_with_no_result_is_assessable_but_not_filled_in() -> None:
    hits = _hits(_FIT_EMPTY, "fit_result")
    assert hits
    assert not any(h["checked"] for h in hits)


def test_printed_but_empty_blood_rows_are_assessable_and_not_filled_in() -> None:
    hits = _hits(_BLOODS_EMPTY, "blood_results")
    assert {h["item_pattern"] for h in hits} == {"Haemoglobin", "Sodium"}
    assert not any(h["checked"] for h in hits)


def test_a_blood_row_with_a_value_counts_as_filled_in() -> None:
    hits = {h["item_pattern"]: h for h in _hits(_BLOODS_RESULTED, "blood_results")}
    assert hits["Haemoglobin"]["checked"] is True
    assert hits["Sodium"]["checked"] is False


def test_a_row_counts_as_filled_in_exactly_when_it_becomes_a_fact() -> None:
    letters = [_FIT_RESULTED, _FIT_EMPTY, _BLOODS_EMPTY, _BLOODS_RESULTED]
    for letter in letters:
        seeded = {
            str(e["text"]).casefold()
            for e in seed_ordered_tests_entities(letter, _schema())
            if e["semantic_tag"] != "observable entity"
        }
        checked = {
            h["item_pattern"].casefold()
            for h in collect_section_hits(_schema(), [letter])
            if h["checked"]
        }
        assert checked == seeded, letter


def _mandatory_bloods() -> list[dict]:
    return [
        {
            "name": "Recent blood results required",
            "kind": "mandatory",
            "required": True,
            "section_id": "blood_results",
        }
    ]


def test_empty_bloods_are_reported_missing_without_degrading_the_run() -> None:
    result = evaluate_completeness_groups(
        _mandatory_bloods(),
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=collect_section_hits(_schema(), [_BLOODS_EMPTY]),
    )
    assert result["complete"] is False
    assert result["degraded"] is False
    assert result["missing_groups"][0]["outcome"] == "not_matched"


def test_resulted_fit_satisfies_a_fit_required_rule() -> None:
    result = evaluate_completeness_groups(
        [
            {
                "name": "FIT required",
                "kind": "mandatory",
                "required": True,
                "section_id": "fit_result",
            }
        ],
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=collect_section_hits(_schema(), [_FIT_RESULTED]),
    )
    assert result["complete"] is True
    assert result["degraded"] is False
