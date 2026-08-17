"""Tests for Knowledge Graph-backed lab result classification."""

from __future__ import annotations

from libs.lab_results.classifier import (
    LabConfigError,
    classify_lab_result,
    get_lab_config,
)
from libs.lab_results.range_select import LabReferenceRange, select_reference_range
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
    allowed = {
        "high",
        "low",
        "out_of_range",
        "critically_high",
        "critically_low",
        "normal",
    }
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


class _NormalSession:
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
                        "classification": "normal",
                        "concept_id": "166618000",
                        "term": "PSA within reference range",
                    }
                ],
            }
        ]


def test_pipeline_emits_within_range_finding_when_mapped(monkeypatch):
    def _classify(*_args, **_kwargs):
        return classify_lab_result(
            "104148003",
            2.0,
            "ug/L",
            patient_sex="male",
            patient_age=55,
            session=_NormalSession(),
        )

    monkeypatch.setattr("libs.lab_results.pipeline.classify_lab_result", _classify)
    entities = [
        {
            "label": "observable_entity",
            "concept_id": "104148003",
            "text": "PSA",
            "value": 2.0,
            "unit": "ug/L",
        }
    ]
    enriched = enrich_lab_result_findings(entities, patient_sex="male", patient_age=55)
    assert enriched[-1]["concept_id"] == "166618000"
    assert enriched[-1]["classification"] == "normal"


def test_pipeline_skips_within_range_when_unmapped(monkeypatch):
    from libs.lab_results.classifier import LabClassification

    def _classify(*_args, **_kwargs):
        return LabClassification(
            concept_id="365616006",
            display_name="Haemoglobin",
            classification="normal",
            canonical_value=163.5,
            canonical_unit="g/L",
            reference_range=None,
            interpretation_concept_id=None,
            interpretation_term=None,
        )

    monkeypatch.setattr("libs.lab_results.pipeline.classify_lab_result", _classify)
    entities = [
        {
            "label": "observable_entity",
            "concept_id": "365616006",
            "text": "Haemoglobin",
            "value": 163.5,
            "unit": "g/L",
        }
    ]
    enriched = enrich_lab_result_findings(entities, patient_sex="male", patient_age=75)
    assert all(not row.get("lab_result_derived") for row in enriched)


def _range_row(range_id: str, high: float, *, org_id: str = "", critical_high=None):
    return {
        "range_id": range_id,
        "sex": "male",
        "age_min": 50,
        "age_max": 59,
        "low": 0,
        "high": high,
        "critical_low": None,
        "critical_high": critical_high,
        "source": "test",
        "org_id": org_id,
    }


class _ScopedSession:
    """Mirrors GET_LAB_RESULT_CONFIG: platform plus the requested org only."""

    def __init__(self, ranges):
        self.ranges = ranges
        self.last_params: dict = {}

    def run(self, _query: str, **params):
        self.last_params = params
        org = str(params.get("org_id") or "")
        include_all = bool(params.get("include_all"))
        visible = [
            row
            for row in self.ranges
            if include_all or not row.get("org_id") or row.get("org_id") == org
        ]
        return [
            {
                "concept_id": "104148003",
                "display_name": "Prostate specific antigen",
                "canonical_unit": "ug/L",
                "source": "test",
                "conversions": [],
                "ranges": visible,
                "interpretations": [],
            }
        ]


def test_org_overlay_wins_over_platform_default():
    session = _ScopedSession(
        [
            _range_row("psa-default", 3.5, critical_high=10),
            _range_row("psa-org-a", 6.0, org_id="org-A"),
        ]
    )
    result = classify_lab_result(
        "104148003",
        5.0,
        "ug/L",
        patient_sex="male",
        patient_age=55,
        session=session,
        org_id="org-A",
    )
    assert result.classification == "normal"
    assert result.reference_range is not None
    assert result.reference_range.range_id == "psa-org-a"
    assert result.reference_range.org_id == "org-A"


def test_missing_org_overlay_falls_back_to_platform_default():
    session = _ScopedSession([_range_row("psa-default", 3.5, critical_high=10)])
    result = classify_lab_result(
        "104148003",
        5.0,
        "ug/L",
        patient_sex="male",
        patient_age=55,
        session=session,
        org_id="org-A",
    )
    assert result.classification == "high"
    assert result.reference_range is not None
    assert result.reference_range.range_id == "psa-default"
    assert result.reference_range.org_id == ""


def test_no_matching_range_fails_closed():
    session = _ScopedSession([_range_row("psa-org-b", 1.0, org_id="org-B")])
    try:
        classify_lab_result(
            "104148003",
            5.0,
            "ug/L",
            patient_sex="male",
            patient_age=55,
            session=session,
            org_id="org-A",
        )
    except LabConfigError as exc:
        assert "No reference range" in str(exc)
    else:
        raise AssertionError("expected LabConfigError")


def test_other_org_overlay_is_not_applied():
    session = _ScopedSession(
        [
            _range_row("psa-default", 3.5, critical_high=10),
            _range_row("psa-org-b", 20.0, org_id="org-B"),
        ]
    )
    result = classify_lab_result(
        "104148003",
        5.0,
        "ug/L",
        patient_sex="male",
        patient_age=55,
        session=session,
        org_id="org-A",
    )
    assert result.reference_range is not None
    assert result.reference_range.range_id == "psa-default"
    assert session.last_params.get("include_all") is False
    assert session.last_params.get("org_id") == "org-A"


def test_overlay_thresholds_are_not_mixed_with_platform_critical():
    default = LabReferenceRange(
        range_id="default",
        low=0,
        high=3.5,
        critical_low=None,
        critical_high=10,
        source="test",
        sex="male",
        age_min=50,
        age_max=59,
    )
    overlay = LabReferenceRange(
        range_id="org-a",
        low=0,
        high=6.0,
        critical_low=None,
        critical_high=None,
        source="test",
        sex="male",
        age_min=50,
        age_max=59,
        org_id="org-A",
    )
    leaked = LabReferenceRange(
        range_id="org-b",
        low=0,
        high=1.0,
        critical_low=None,
        critical_high=None,
        source="test",
        sex="male",
        age_min=50,
        age_max=59,
        org_id="org-B",
    )
    band = select_reference_range(
        [default, overlay, leaked],
        sex="male",
        age_years=55,
        org_id="org-A",
    )
    assert band is not None
    assert band.range_id == "org-a"
    assert band.critical_high is None
