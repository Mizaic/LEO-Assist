"""Tests for benchmark_loader.py — flattening with ODS linkage."""

from __future__ import annotations

import pytest

from services.fhir_api.app.services.benchmark_loader import (
    _build_entity_map,
    _flatten_simple_value,
    _flatten_ncda,
    flatten_benchmarks,
)


# ---------------------------------------------------------------------------
# _build_entity_map
# ---------------------------------------------------------------------------

class TestBuildEntityMap:
    def test_practice_uses_ods_as_scope_id(self):
        entities = [
            {"id": "e1", "type": "gp_practice", "name": "Woodbrook Medical Centre", "ods_code": "C84070"},
        ]
        m = _build_entity_map(entities)
        assert "e1" in m
        assert m["e1"]["scope_id"] == "C84070"
        assert m["e1"]["scope_name"] == "Woodbrook Medical Centre"
        assert m["e1"]["scope_type"] == "gp_practice"

    def test_practice_without_ods_uses_entity_id(self):
        entities = [
            {"id": "e_noids", "type": "gp_practice", "name": "Unknown Practice"},
        ]
        m = _build_entity_map(entities)
        assert m["e_noids"]["scope_id"] == "e_noids"

    def test_national_uses_entity_id(self):
        entities = [
            {"id": "england", "type": "national", "name": "England"},
        ]
        m = _build_entity_map(entities)
        assert m["england"]["scope_id"] == "england"

    def test_cancer_alliance_uses_entity_id(self):
        entities = [
            {"id": "em_alliance", "type": "cancer_alliance", "name": "East Midlands"},
        ]
        m = _build_entity_map(entities)
        assert m["em_alliance"]["scope_id"] == "em_alliance"

    def test_empty_entities(self):
        assert _build_entity_map([]) == {}

    def test_skips_entities_without_id(self):
        entities = [{"type": "national", "name": "England"}]
        assert _build_entity_map(entities) == {}


# ---------------------------------------------------------------------------
# _flatten_simple_value
# ---------------------------------------------------------------------------

class TestFlattenSimpleValue:
    def _entity_map(self):
        return {
            "e1": {"scope_type": "gp_practice", "scope_name": "Test Practice", "scope_id": "ODS001", "ods_code": "ODS001"},
            "nat": {"scope_type": "national", "scope_name": "England", "scope_id": "england", "ods_code": ""},
        }

    def test_scalar_value_uses_canonical_scope_id(self):
        result = _flatten_simple_value(
            "e1", 42.5, "primary_care_interval", "primary_care_interval.median_days",
            "Median PCI days", "days", self._entity_map(), "ncda-2018", "NCDA 2018",
        )
        assert len(result) == 1
        assert result[0]["scope_id"] == "ODS001"
        assert result[0]["scope_type"] == "gp_practice"
        assert result[0]["value"] == 42.5

    def test_national_scope_id_preserved(self):
        result = _flatten_simple_value(
            "nat", 30.0, "primary_care_interval", "primary_care_interval.median_days",
            "Median PCI days", "days", self._entity_map(), "ncda-2018", "NCDA 2018",
        )
        assert result[0]["scope_id"] == "england"
        assert result[0]["scope_type"] == "national"

    def test_unknown_entity_returns_empty(self):
        result = _flatten_simple_value(
            "unknown_entity", 10, "cat", "cat.metric", "Label", "pct", self._entity_map(), "ncda-2018", "NCDA",
        )
        assert result == []

    def test_composite_sex_stored_as_value_json(self):
        result = _flatten_simple_value(
            "e1", {"male": 48.0, "female": 52.0}, "demographics", "demographics.sex",
            "Sex", "pct", self._entity_map(), "ncda-2018", "NCDA 2018",
        )
        assert len(result) == 1
        assert result[0]["value"] is None
        assert result[0]["value_json"] == {"male": 48.0, "female": 52.0}

    def test_dict_value_expands_to_sub_keys(self):
        result = _flatten_simple_value(
            "nat", {"early": 40, "late": 60}, "cancer_stage", "cancer_stage.proportion",
            "Stage", "pct", self._entity_map(), "ncda-2018", "NCDA 2018",
        )
        assert len(result) == 2
        metric_ids = {r["metric_id"] for r in result}
        assert "cancer_stage.proportion.early" in metric_ids
        assert "cancer_stage.proportion.late" in metric_ids


# ---------------------------------------------------------------------------
# _flatten_ncda (integration-style)
# ---------------------------------------------------------------------------

class TestFlattenNcda:
    def _minimal_ncda(self):
        return {
            "entities": [
                {"id": "e1", "type": "gp_practice", "name": "Test Practice", "ods_code": "C84070"},
                {"id": "nat", "type": "national", "name": "England"},
                {"id": "em", "type": "cancer_alliance", "name": "East Midlands"},
            ],
            "benchmarks": {
                "primary_care_interval": {
                    "median_days": {
                        "label": "Median PCI days",
                        "unit": "days",
                        "values": {"e1": 30, "nat": 25, "em": 27},
                    }
                }
            },
        }

    def test_practice_scope_id_is_ods(self):
        rows = _flatten_ncda(self._minimal_ncda(), "ncda-2018", "NCDA 2018")
        practice_rows = [r for r in rows if r["scope_type"] == "gp_practice"]
        assert len(practice_rows) == 1
        assert practice_rows[0]["scope_id"] == "C84070"

    def test_national_scope_id_is_entity_id(self):
        rows = _flatten_ncda(self._minimal_ncda(), "ncda-2018", "NCDA 2018")
        nat_rows = [r for r in rows if r["scope_type"] == "national"]
        assert nat_rows[0]["scope_id"] == "nat"

    def test_all_entities_produce_rows(self):
        rows = _flatten_ncda(self._minimal_ncda(), "ncda-2018", "NCDA 2018")
        scope_types = {r["scope_type"] for r in rows}
        assert "gp_practice" in scope_types
        assert "national" in scope_types
        assert "cancer_alliance" in scope_types

    def test_audit_id_is_set(self):
        rows = _flatten_ncda(self._minimal_ncda(), "ncda-2018", "NCDA 2018")
        assert all(r["audit_id"] == "ncda-2018" for r in rows)


# ---------------------------------------------------------------------------
# flatten_benchmarks (top-level)
# ---------------------------------------------------------------------------

class TestFlattenBenchmarks:
    def test_ncda_template_produces_values(self):
        raw = {
            "audit": {"year": 2018, "name": "NCDA 2018"},
            "entities": [
                {"id": "nat", "type": "national", "name": "England"},
            ],
            "benchmarks": {
                "primary_care_interval": {
                    "median_days": {"label": "Median", "unit": "days", "values": {"nat": 25}},
                }
            },
        }
        rows = flatten_benchmarks(raw, template_id="ncda")
        assert len(rows) > 0
        assert rows[0]["audit_id"] == "ncda-2018"

    def test_audit_id_override(self):
        raw = {
            "audit": {"year": 2018, "name": "NCDA 2018"},
            "entities": [{"id": "nat", "type": "national", "name": "England"}],
            "benchmarks": {
                "primary_care_interval": {
                    "median_days": {"label": "Median", "unit": "days", "values": {"nat": 25}},
                }
            },
        }
        rows = flatten_benchmarks(raw, template_id="ncda", audit_id="custom-id")
        assert all(r["audit_id"] == "custom-id" for r in rows)

    def test_no_template_no_mapping_returns_empty(self):
        rows = flatten_benchmarks({"foo": "bar"})
        assert rows == []
