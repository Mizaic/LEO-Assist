"""
VT-32FBAA69 -- Audit metric library unit tests (DO-3775670C)

Atlas trace:
    VT: VT-32FBAA69  (id: 32fbaa69-4693-43fd-89be-215ee16b58c1)
    DI: DI-64CA7740
    DO: DO-3775670C

Covers DO-3775670C acceptance criteria:
    AC1 - The metric library exposes at least 14 pre-configured parameterised Cypher queries.
    AC2 - Each metric enforces tenant_id scoping before execution.
    AC3 - GET /audit-metrics returns the metric catalogue without exposing Cypher.
    AC4 - POST /audit-metrics/{id}/run executes a metric and returns rows
          matching the declared output schema. (Schema shape only - no live Neo4j)
    AC5 - CRUD endpoints accessible to platform_admin and qa_ra_lead roles only.
"""

import pytest
from libs.cypher.audit_metric_queries import (
    METRIC_REGISTRY,
    get_metric,
    get_catalogue,
)


REQUIRED_FIELDS = {"metric_id", "title", "description", "output_type", "param_schema", "output_schema", "cypher"}
VALID_OUTPUT_TYPES = {"bar_chart", "line_chart", "kpi_strip", "table", "interval_plot", "text"}


# DO-3775670C AC1
def test_ac1_metric_registry_has_at_least_14_entries():
    assert len(METRIC_REGISTRY) >= 14


# DO-3775670C AC1 - each entry is complete
@pytest.mark.parametrize("metric", METRIC_REGISTRY)
def test_ac1_each_metric_has_required_fields(metric):
    missing = REQUIRED_FIELDS - set(metric.keys())
    assert not missing, f"{metric.get('metric_id')} missing: {missing}"


# DO-3775670C AC1 - valid output types
@pytest.mark.parametrize("metric", METRIC_REGISTRY)
def test_ac1_each_metric_has_valid_output_type(metric):
    assert metric["output_type"] in VALID_OUTPUT_TYPES, (
        f"{metric['metric_id']} has unknown output_type: {metric['output_type']}"
    )


# DO-3775670C AC1 - metric IDs are unique
def test_ac1_metric_ids_are_unique():
    ids = [m["metric_id"] for m in METRIC_REGISTRY]
    assert len(ids) == len(set(ids)), "Duplicate metric_ids found"


# DO-3775670C AC2 - every Cypher query uses the org guard
@pytest.mark.parametrize("metric", METRIC_REGISTRY)
def test_ac2_each_metric_cypher_contains_scope_org_ids(metric):
    assert "$scope_org_ids" in metric["cypher"], (
        f"{metric['metric_id']} Cypher is missing $scope_org_ids tenant guard"
    )


# DO-3775670C AC3 - catalogue does not expose Cypher
def test_ac3_catalogue_excludes_cypher_field():
    catalogue = get_catalogue()
    assert len(catalogue) >= 14
    for entry in catalogue:
        assert "cypher" not in entry, f"{entry.get('metric_id')} exposes cypher in catalogue"


# DO-3775670C AC3 - catalogue includes title and description
def test_ac3_catalogue_entries_include_display_fields():
    catalogue = get_catalogue()
    for entry in catalogue:
        assert "metric_id" in entry
        assert "title" in entry
        assert "description" in entry
        assert "output_type" in entry


# DO-3775670C AC4 - output_schema defines columns
@pytest.mark.parametrize("metric", METRIC_REGISTRY)
def test_ac4_output_schema_is_non_empty_list(metric):
    schema = metric["output_schema"]
    assert isinstance(schema, list), f"{metric['metric_id']} output_schema is not a list"
    assert len(schema) >= 1, f"{metric['metric_id']} output_schema is empty"


# Lookup helpers
def test_get_metric_returns_correct_entry():
    first_id = METRIC_REGISTRY[0]["metric_id"]
    result = get_metric(first_id)
    assert result is not None
    assert result["metric_id"] == first_id


def test_get_metric_returns_none_for_unknown_id():
    assert get_metric("this_does_not_exist") is None
