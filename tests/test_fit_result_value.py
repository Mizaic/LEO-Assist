"""A taught FIT result carries its value, and a positive one gives the finding.

The seeder already checks that the taught result label is followed by a
value before it seeds the result. The value must also reach the fact, or
the lab step has nothing to classify. A reading with a comparator only
gives a finding when the comparator cannot change the answer: "> 200"
is high against a limit of 9.9, but "< 10" is never high.

Atlas trace:
  DI: DI-5C9CA57B
  DO: DO-E2F2B277
  VT: VT-1B2063CC
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from libs.lab_results.classifier import classify_lab_result
from libs.lab_results.pipeline import (
    enrich_lab_result_findings,
    observations_from_entities,
)
from libs.pipeline.form_schema_seeding import (
    is_taught_test_row,
    seed_ordered_tests_entities,
)
from libs.pipeline_graph.subgraphs.terminology import _resolve_terms
from libs.terminology.client import ResolvedTerm, TerminologyClient
from tests.test_form_schema_single_result_row import (
    FIT_SCHEMA,
    OBSERVABLE_ID,
    RESULTED_TEXT,
)

POSITIVE_FINDING = "71711000112103"

MODEL_FINDING = {"text": "positive FIT", "label": "finding", "assertion": "present"}
MODEL_RESULT = {
    "text": "FIT",
    "label": "observable_entity",
    "value": "200",
    "unit": "ug/g",
    "assertion": "present",
}
LOOKUPS = {
    "positive FIT": ResolvedTerm(
        text="positive FIT",
        concept_id=POSITIVE_FINDING,
        term="Occult blood detected in feces by immunoassay",
        semantic_tag="finding",
        score=1.0,
    ),
    "FIT": ResolvedTerm(
        text="FIT",
        concept_id=OBSERVABLE_ID,
        term="Quantitative faecal immunochemical test",
        semantic_tag="observable entity",
        score=0.95,
    ),
}


class _FitConfigSession:
    def run(self, _query: str, **_params):
        return [
            {
                "concept_id": OBSERVABLE_ID,
                "display_name": "Faecal immunochemical test result",
                "canonical_unit": "ug/g",
                "source": "test",
                "conversions": [],
                "ranges": [
                    {
                        "range_id": "fit-all",
                        "sex": "all",
                        "age_min": None,
                        "age_max": None,
                        "low": None,
                        "high": 9.9,
                        "critical_low": None,
                        "critical_high": None,
                        "source": "test",
                    }
                ],
                "interpretations": [
                    {
                        "classification": "high",
                        "concept_id": POSITIVE_FINDING,
                        "term": "Occult blood detected in feces by immunoassay",
                    }
                ],
            }
        ]


@pytest.fixture(autouse=True)
def _fit_config(monkeypatch):
    def _classify(concept_id, value, unit, **kwargs):
        return classify_lab_result(
            concept_id, value, unit, session=_FitConfigSession(), **kwargs
        )

    monkeypatch.setattr("libs.lab_results.pipeline.classify_lab_result", _classify)


def _result_seed(text: str = RESULTED_TEXT) -> dict:
    seeds = seed_ordered_tests_entities(text, FIT_SCHEMA)
    return next(e for e in seeds if e["semantic_tag"] == "observable entity")


def _with_reading(value: str) -> dict:
    return {**_result_seed(), "value": value, "unit": "ug/g"}


def _derived(entity: dict) -> list[dict]:
    enriched = enrich_lab_result_findings([entity], patient_sex=None, patient_age=None)
    return [e for e in enriched if e.get("lab_result_derived")]


def test_result_seed_carries_the_row_value_and_unit():
    seed = _result_seed()
    assert seed["value"] == "> 200"
    assert seed["unit"] == "ug/g"


def test_positive_fit_gives_the_finding_with_its_value():
    derived = _derived(_result_seed())
    assert [d["concept_id"] for d in derived] == [POSITIVE_FINDING]
    assert derived[0]["value"] == 200.0
    assert derived[0]["value_comparator"] == ">"


@pytest.mark.parametrize("value", ["< 10", "< 4", "4", "> 5", "9.9"])
def test_a_reading_that_is_not_surely_high_gives_no_finding(value):
    assert _derived(_with_reading(value)) == []


def test_comparator_readings_stay_out_of_guideline_observations():
    assert observations_from_entities([_with_reading("> 200")]) == []


def _resolve(entities: list[dict], lookups: dict | None = None) -> list[dict]:
    table = {**LOOKUPS, **(lookups or {})}

    def _fake_resolve(self, terms, expected_tags=None, org_id=None):
        return {t: [table[t]] if t in table else [] for t in terms}

    with patch.object(TerminologyClient, "resolve", _fake_resolve):
        result = _resolve_terms(
            {"entities": entities, "expected_tags": {}, "confidence_threshold": 0.55}
        )
    return result["resolved_entities"]


def _seeds() -> list[dict]:
    return seed_ordered_tests_entities(RESULTED_TEXT, FIT_SCHEMA)


def _coded(entities: list[dict], concept_id: str) -> list[dict]:
    return [e for e in entities if e.get("concept_id") == concept_id]


def test_the_finding_keeps_its_value_beside_the_models_copy():
    findings = _coded(_resolve([dict(MODEL_FINDING), *_seeds()]), POSITIVE_FINDING)
    assert len(findings) == 1
    assert findings[0]["value"] == 200.0
    assert findings[0]["value_comparator"] == ">"


def test_the_taught_result_wins_over_the_models_copy():
    resolved = _resolve([dict(MODEL_RESULT), *_seeds()])
    results = _coded(resolved, OBSERVABLE_ID)
    assert len(results) == 1
    assert is_taught_test_row(results[0])
    assert results[0]["value"] == "> 200"
    findings = _coded(resolved, POSITIVE_FINDING)
    assert [f["value_comparator"] for f in findings] == [">"]


def test_ordinary_copies_still_keep_the_higher_score():
    weaker = replace(LOOKUPS["FIT"], text="FIT test", score=0.6)
    resolved = _resolve(
        [{"text": "FIT test", "label": "observable_entity"}, dict(MODEL_RESULT)],
        {"FIT test": weaker},
    )
    assert [e["text"] for e in _coded(resolved, OBSERVABLE_ID)] == ["FIT"]
