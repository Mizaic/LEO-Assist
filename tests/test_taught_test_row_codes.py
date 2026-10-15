"""Taught test-row codes survive the terminology step.

A form teacher can teach the SNOMED code for a test row (the procedure)
and for the result it reports (the observable). Those codes must reach
the fact. A second lookup of the row's printed label must not replace
them, clear them, or mark the fact unresolved, and the coding verifier
must not drop them: like a taught tick, a person chose the code.

Atlas trace:
  DI: DI-5C9CA57B
  DO: DO-E2F2B277
  VT: VT-1B2063CC
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from libs.lab_results.classifier import LabConfigError
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline_graph.subgraphs.coding_verifier import _verify_entities
from libs.pipeline_graph.subgraphs.extraction import _enrich_with_blood_panel_entities
from libs.pipeline_graph.subgraphs.terminology import _resolve_terms
from libs.terminology.client import ResolvedTerm, TerminologyClient

ROW_LABEL = "Faecal Immunochemical test result ug/g"
PROCEDURE_ID = "441579003"
OBSERVABLE_ID = "1049361000000101"
TEXT = f"Faecal immunochemical test result\n| {ROW_LABEL} > 200 ug/g |  |  |\n"


@pytest.fixture(autouse=True)
def _no_lab_config(monkeypatch):
    """Keep the lab step off the Knowledge Graph; its findings are tested
    in ``tests/test_fit_result_value.py``."""

    def _unconfigured(concept_id, *_args, **_kwargs):
        raise LabConfigError(f"no lab config for {concept_id} in this test")

    monkeypatch.setattr("libs.lab_results.pipeline.classify_lab_result", _unconfigured)


def _schema(procedure: str = PROCEDURE_ID, observable: str = OBSERVABLE_ID):
    item = FormSchemaItem(
        pattern=ROW_LABEL,
        entity_text="Faecal immunochemical test",
        semantic_tag="procedure",
        assertion="present",
        procedure_snomed=procedure,
        procedure_display="Measurement of occult blood in stool specimen",
        analytes=[
            {
                "label": ROW_LABEL,
                "snomed_code": observable,
                "display": "Faecal immunochemical test result",
            }
        ],
    )
    section = FormSection(
        section_id="fit_result",
        section_type="ordered_tests",
        label="Faecal immunochemical test result",
        start_pattern="",
        items=[item],
    )
    return FormSchema(
        schema_id="test-fit-row",
        fingerprint="fp-fit-row",
        form_name="Test lower GI form",
        created_by="test",
        sections=[section],
    )


def _resolve(entities, candidates):
    def _fake_resolve(self, terms, expected_tags=None, org_id=None):
        return {term: list(candidates) for term in terms}

    with patch.object(TerminologyClient, "resolve", _fake_resolve):
        result = _resolve_terms(
            {"entities": entities, "expected_tags": {}, "confidence_threshold": 0.55}
        )
    return result["resolved_entities"]


def _by_tag(entities):
    return {e.get("semantic_tag"): e for e in entities}


WRONG_HIT = ResolvedTerm(
    text=ROW_LABEL,
    concept_id="999999999",
    term="Wrong long-label hit",
    semantic_tag="procedure",
    score=0.99,
)


def test_seeded_test_row_facts_carry_the_taught_codes():
    seeded = _by_tag(seed_ordered_tests_entities(TEXT, _schema()))
    assert seeded["procedure"]["concept_id"] == PROCEDURE_ID
    assert seeded["observable entity"]["concept_id"] == OBSERVABLE_ID


def test_taught_codes_are_not_replaced_by_a_label_lookup():
    seeded = seed_ordered_tests_entities(TEXT, _schema())
    resolved = _by_tag(_resolve(seeded, [WRONG_HIT]))
    assert resolved["procedure"]["concept_id"] == PROCEDURE_ID
    assert resolved["observable entity"]["concept_id"] == OBSERVABLE_ID


def test_taught_codes_stay_resolved_when_the_lookup_finds_nothing():
    seeded = seed_ordered_tests_entities(TEXT, _schema())
    for entity in _resolve(seeded, []):
        assert entity["concept_id"] in {PROCEDURE_ID, OBSERVABLE_ID}
        assert entity.get("terminology_unresolved") is not True


def _verify(entities, verdict):
    rows = [
        {"index": i, "verdict": verdict, "better_term": None, "reason": "test"}
        for i in range(len(entities))
    ]
    with patch(
        "libs.pipeline_graph.subgraphs.coding_verifier.verify_coding_batch",
        return_value=rows,
    ) as batch:
        result = _verify_entities(
            {"entities": entities, "encounter_text": TEXT, "errors": []}
        )
    return result["entities"], batch


def test_coding_verifier_does_not_drop_taught_codes():
    resolved = _resolve(seed_ordered_tests_entities(TEXT, _schema()), [])
    verified, _ = _verify(resolved, "not_codeable")
    for entity in verified:
        assert entity["concept_id"] in {PROCEDURE_ID, OBSERVABLE_ID}
        assert entity.get("terminology_unresolved") is not True


def test_coding_verifier_still_checks_a_looked_up_row_code():
    seeded = seed_ordered_tests_entities(TEXT, _schema(procedure="", observable=""))
    looked_up = ResolvedTerm(
        text=ROW_LABEL,
        concept_id="441579003",
        term="Measurement of occult blood in stool specimen using immunoassay",
        semantic_tag="procedure",
        score=0.9,
    )
    resolved = [e for e in _resolve(seeded, [looked_up]) if e.get("concept_id")]
    verified, batch = _verify(resolved, "not_codeable")
    assert batch.called
    assert all(e.get("concept_id") is None for e in verified)


def test_a_row_with_no_taught_code_is_still_looked_up():
    seeded = seed_ordered_tests_entities(TEXT, _schema(procedure="", observable=""))
    looked_up = ResolvedTerm(
        text=ROW_LABEL,
        concept_id="441579003",
        term="Measurement of occult blood in stool specimen using immunoassay",
        semantic_tag="procedure",
        score=0.99,
    )
    resolved = _by_tag(_resolve(seeded, [looked_up]))
    assert resolved["procedure"]["concept_id"] == "441579003"


def _merged(model_facts, schema):
    result = _enrich_with_blood_panel_entities(
        {"entities": [dict(f) for f in model_facts]}, TEXT, [], schema=schema
    )
    return result["entities"]


MODEL_TEST = {"text": ROW_LABEL, "label": "procedure", "semantic_tag": "procedure"}
MODEL_RESULT = {
    "text": ROW_LABEL,
    "label": "observable_entity",
    "semantic_tag": "observable entity",
    "value": "200",
}


def test_a_taught_row_replaces_the_models_same_text_fact():
    merged = _merged([MODEL_TEST], _schema())
    assert [e.get("concept_id") for e in merged] == [PROCEDURE_ID, OBSERVABLE_ID]
    assert all(e.get("__source") == "form_schema_ordered_tests" for e in merged)


def test_a_taught_result_replaces_the_models_result_of_the_same_text():
    merged = _by_tag(_merged([MODEL_TEST, MODEL_RESULT], _schema()))
    assert merged["procedure"]["concept_id"] == PROCEDURE_ID
    assert merged["observable entity"]["concept_id"] == OBSERVABLE_ID
    assert merged["observable entity"]["value"] == "> 200"


def test_a_row_taught_without_a_code_still_gives_way_to_the_model():
    merged = _merged([MODEL_TEST], _schema(procedure="", observable=""))
    assert merged == [MODEL_TEST]
