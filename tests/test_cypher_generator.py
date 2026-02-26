"""Tests for the Cypher generator (no-code measure builder)."""

from __future__ import annotations

import pytest

from services.fhir_api.app.services.cypher_generator import generate_cypher


def test_generate_episodes_by_cancer_type():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": "cancer_type",
        "scopeType": "gp",
    }
    cypher, params = generate_cypher(definition)
    assert "$practiceOdsCode" in cypher
    assert "HAS_EPISODE" in cypher
    assert "CancerEpisode" in cypher
    assert "cancer_type" in cypher
    assert "RETURN coalesce(toString(ep.cancer_type)" in cypher
    assert "ORDER BY value DESC" in cypher


def test_generate_total_with_filters():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [
            {"property": "cancer_type", "op": "eq", "value": "Lung"},
            {"property": "status", "op": "neq", "value": "merged"},
        ],
        "groupBy": None,
        "scopeType": "icb",
    }
    cypher, params = generate_cypher(definition)
    assert "$icbOdsCode" in cypher
    assert "COMMISSIONED_BY" in cypher
    assert "ICB" in cypher
    assert "f0_cancer_type" in params or "cancer_type" in str(params)
    assert params.get("f0_cancer_type") == "Lung" or "Lung" in str(params)


def test_generate_patients_total():
    definition = {
        "nodeLabel": "Patient",
        "filters": [],
        "groupBy": None,
        "scopeType": "alliance",
    }
    cypher, params = generate_cypher(definition)
    assert "$allianceOdsCode" in cypher
    assert "CancerAlliance" in cypher
    assert "RETURN 'Total' AS name, count(*) AS value" in cypher


def test_invalid_node_label_raises():
    with pytest.raises(ValueError, match="Unknown nodeLabel"):
        generate_cypher({"nodeLabel": "UnknownNode", "scopeType": "gp"})


def test_invalid_scope_type_raises():
    with pytest.raises(ValueError, match="Unknown scopeType"):
        generate_cypher({"nodeLabel": "CancerEpisode", "scopeType": "invalid"})


def test_nin_operator_excludes_cancer_types():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [
            {"property": "cancer_type", "op": "nin", "value": ["breast", "prostate", "gynaecological"]},
        ],
        "groupBy": "Patient.gender",
        "scopeType": "gp",
    }
    cypher, params = generate_cypher(definition)
    assert "NOT (ep.cancer_type IN " in cypher or "NOT (ep.cancer_type IN $" in cypher
    assert "f0_cancer_type" in params
    assert params["f0_cancer_type"] == ["breast", "prostate", "gynaecological"]


def test_cohort_and_nin_filter_no_duplicate_where():
    """Regression: cohort + nin filter must not produce 'AND WHERE NOT' (invalid Cypher)."""
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [
            {"property": "cancer_type", "op": "nin", "value": ["breast", "lung"]},
        ],
        "groupBy": "Patient.gender",
        "scopeType": "gp",
        "cohortVariant": "diagnosed",
    }
    cypher, params = generate_cypher(definition)
    assert "AND WHERE " not in cypher, "Invalid Cypher: duplicate WHERE clause"
    assert "ep.status = $_cohort_status" in cypher and "NOT (ep.cancer_type IN $" in cypher


def test_patient_gender_groupby():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": "Patient.gender",
        "scopeType": "gp",
    }
    cypher, params = generate_cypher(definition)
    assert "p.gender" in cypher
    assert "RETURN coalesce(toString(p.gender)" in cypher


def test_cohort_filter_diagnosed():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": "cancer_type",
        "scopeType": "gp",
        "cohortVariant": "diagnosed",
    }
    cypher, params = generate_cypher(definition)
    assert "ep.status = $_cohort_status" in cypher
    assert params.get("_cohort_status") == "confirmed"


def test_cohort_filter_all_referred():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [{"property": "cancer_type", "op": "eq", "value": "lung"}],
        "groupBy": None,
        "scopeType": "gp",
        "cohortVariant": "all_referred",
    }
    cypher, params = generate_cypher(definition)
    assert "ep.status IN $_cohort_statuses" in cypher
    assert params.get("_cohort_statuses") == ["confirmed", "excluded", "inconclusive"]
    assert "ep.cancer_type" in cypher


def test_age_band_at_diagnosis_groupby():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": "Patient.age_band_at_diagnosis",
        "scopeType": "gp",
    }
    cypher, params = generate_cypher(definition)
    assert "duration.between" in cypher
    assert "0-24" in cypher
    assert "85+" in cypher
    assert "age_band" in cypher


def test_median_aggregation():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": None,
        "scopeType": "gp",
        "aggregation": "median",
        "valueProperty": "primary_care_interval_days",
    }
    cypher, params = generate_cypher(definition)
    assert "percentileCont" in cypher
    assert "first_presentation_date" in cypher
    assert "referral_date" in cypher
    assert "Median" in cypher
    assert "iqr_low" in cypher
    assert "iqr_high" in cypher


def test_median_age_at_diagnosis():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": None,
        "scopeType": "gp",
        "aggregation": "median",
        "valueProperty": "age_at_diagnosis",
    }
    cypher, params = generate_cypher(definition)
    assert "percentileCont" in cypher
    assert "birthDate" in cypher
    assert "diagnosis_date" in cypher
    assert "Median" in cypher


def test_percentage_aggregation():
    definition = {
        "nodeLabel": "CancerEpisode",
        "filters": [],
        "groupBy": None,
        "scopeType": "gp",
        "aggregation": "percentage",
        "percentageProperty": "safety_netting_recorded",
    }
    cypher, params = generate_cypher(definition)
    assert "pct_val" in params
    assert params["pct_val"] is True
    assert "safety_netting_recorded" in cypher
    assert "100.0" in cypher


def test_encounter_count_per_patient_band():
    definition = {
        "nodeLabel": "Encounter",
        "filters": [],
        "groupBy": "count_per_patient_band",
        "scopeType": "gp",
    }
    cypher, params = generate_cypher(definition)
    assert "HAS_ENCOUNTER" in cypher
    assert "count(e) AS cnt" in cypher
    assert "<3" in cypher
    assert "3+" in cypher
    assert "band" in cypher


def test_encounter_median_count_per_patient():
    definition = {
        "nodeLabel": "Encounter",
        "filters": [],
        "groupBy": None,
        "scopeType": "gp",
        "aggregation": "median",
        "valueProperty": "count_per_patient",
    }
    cypher, params = generate_cypher(definition)
    assert "HAS_ENCOUNTER" in cypher
    assert "count(e) AS cnt" in cypher
    assert "collect(cnt)" in cypher
    assert "percentileCont" in cypher
    assert "Median" in cypher
