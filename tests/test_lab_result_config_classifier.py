"""Tests for Knowledge Graph-backed lab result classification."""

from __future__ import annotations

from libs.lab_results.classifier import classify_lab_result
from libs.lab_results.pipeline import (
    enrich_lab_result_findings,
    observations_from_entities,
)


class _Session:
    def run(self, _query: str, **_params):
        return [
            {
                "concept_id": "104148003",
                "display_name": "Prostate specific antigen",
                "canonical_unit": "ug/L",
                "source": "test",
                "conversions": [{"unit": "ng/mL", "factor": 1.0, "offset": 0.0}],
                "ranges": [
                    {
                        "range_id": "psa-50-59",
                        "sex": "male",
                        "age_min": 50,
                        "age_max": 59,
                        "low": 0,
                        "high": 3.5,
                        "critical_low": None,
                        "critical_high": 10,
                        "source": "test",
                    }
                ],
                "interpretations": [
                    {
                        "classification": "high",
                        "concept_id": "396152005",
                        "term": "PSA above reference range",
                    }
                ],
            }
        ]


def test_classifier_converts_selects_range_and_returns_interpretation():
    result = classify_lab_result(
        "104148003",
        5.0,
        "ng/mL",
        patient_sex="male",
        patient_age=55,
        session=_Session(),
    )

    assert result.classification == "high"
    assert result.canonical_value == 5.0
    assert result.reference_range is not None
    assert result.reference_range.range_id == "psa-50-59"
    assert result.interpretation_concept_id == "396152005"


def test_pipeline_builds_observations_and_derived_findings(monkeypatch):
    def _classify(*_args, **_kwargs):
        return classify_lab_result(
            "104148003",
            5.0,
            "ug/L",
            patient_sex="male",
            patient_age=55,
            session=_Session(),
        )

    monkeypatch.setattr("libs.lab_results.pipeline.classify_lab_result", _classify)
    entities = [
        {
            "label": "observable_entity",
            "concept_id": "104148003",
            "text": "PSA",
            "value": 5.0,
            "unit": "ug/L",
            "observed_at": "2026-05-01T00:00:00+00:00",
        }
    ]

    observations = observations_from_entities(entities)
    enriched = enrich_lab_result_findings(entities, patient_sex="male", patient_age=55)

    assert observations == [
        {
            "observable_id": "104148003",
            "value": 5.0,
            "unit": "ug/L",
            "observed_at": "2026-05-01T00:00:00+00:00",
        }
    ]
    assert enriched[-1]["concept_id"] == "396152005"
    assert enriched[-1]["lab_result_derived"] is True
