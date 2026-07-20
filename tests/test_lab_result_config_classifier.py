"""Tests for Knowledge Graph-backed lab result classification."""

from __future__ import annotations

from libs.lab_results.classifier import classify_lab_result, get_lab_config
from libs.lab_results.concept_aliases import resolve_lab_config_concept_id
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


def test_uk_haemoglobin_and_amylase_alias_to_seeded_configs():
    assert resolve_lab_config_concept_id("1107511000000100") == "365616006"
    assert resolve_lab_config_concept_id("997491000000108") == "104187009"
    assert resolve_lab_config_concept_id("365616006") == "365616006"


class _HbSession:
    def run(self, _query: str, **params):
        concept_id = str(params.get("concept_id") or "")
        if concept_id != "365616006":
            return []
        return [
            {
                "concept_id": "365616006",
                "display_name": "Haemoglobin",
                "canonical_unit": "g/L",
                "source": "test",
                "conversions": [{"unit": "g/dL", "factor": 10.0, "offset": 0.0}],
                "ranges": [
                    {
                        "range_id": "hb-male",
                        "sex": "male",
                        "age_min": 18,
                        "age_max": None,
                        "low": 130,
                        "high": 180,
                        "critical_low": 70,
                        "critical_high": 200,
                        "source": "test",
                    }
                ],
                "interpretations": [],
            }
        ]


def test_get_lab_config_resolves_uk_haemoglobin_alias():
    config = get_lab_config("1107511000000100", session=_HbSession(), use_cache=False)
    assert config is not None
    assert config.concept_id == "365616006"
    assert config.canonical_unit == "g/L"


def test_classify_uk_haemoglobin_alias_uses_canonical_ranges():
    result = classify_lab_result(
        "1107511000000100",
        163.5,
        "g/L",
        patient_sex="male",
        patient_age=75,
        session=_HbSession(),
    )
    assert result.classification == "normal"
    assert result.canonical_unit == "g/L"


def test_lab_interprets_as_defaults_cover_haemoglobin_and_amylase():
    from pathlib import Path
    import json

    path = (
        Path(__file__).resolve().parents[1]
        / "configs"
        / "reference_ranges"
        / "lab_interprets_as_defaults.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_name = {g["display_name"]: g for g in payload["mappings"]}
    hb = by_name["Haemoglobin"]["interpretations"]
    amy = by_name["Amylase"]["interpretations"]
    assert hb["high"]["concept_id"] == "131141003"
    assert hb["low"]["concept_id"] == "165397008"
    assert amy["high"]["concept_id"] == "275739007"
    assert "1107511000000100" in by_name["Haemoglobin"]["concept_ids"]
    assert "997491000000108" in by_name["Amylase"]["concept_ids"]
    allowed = {"high", "low", "out_of_range", "critically_high", "critically_low"}
    for group in payload["mappings"]:
        for band in group["interpretations"]:
            assert band in allowed


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
