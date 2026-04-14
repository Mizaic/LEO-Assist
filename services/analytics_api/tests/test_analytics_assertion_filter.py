"""Tests for assertion-aware CCI scoring and cohort filtering.

Verifies that 'absent' and other non-confirmed assertions are excluded
from CCI score calculations and cohort condition/smoking filters.
"""

from __future__ import annotations

import sys
import types
import unittest.mock as mock

# -- Stub Azure SDK modules not available in test environments ----
azure_mod = types.ModuleType("azure")
azure_identity_mod = types.ModuleType("azure.identity")
azure_keyvault_mod = types.ModuleType("azure.keyvault")
azure_keyvault_secrets_mod = types.ModuleType("azure.keyvault.secrets")


class _DummyAzureClient:
    def __init__(self, *args, **kwargs):
        _ = (args, kwargs)


azure_identity_mod.DefaultAzureCredential = _DummyAzureClient
azure_keyvault_secrets_mod.SecretClient = _DummyAzureClient
sys.modules.setdefault("azure", azure_mod)
sys.modules.setdefault("azure.identity", azure_identity_mod)
sys.modules.setdefault("azure.keyvault", azure_keyvault_mod)
sys.modules.setdefault("azure.keyvault.secrets", azure_keyvault_secrets_mod)

from services.analytics_api.app.routers import cci as cci_mod  # noqa: E402
from services.analytics_api.app.routers.cohorts import (  # noqa: E402
    CohortFilter,
    _build_where_clauses,
    _CONFIRMED_ASSERTIONS,
)

# -- CCI query tests -------------------------------------------------


def _run_cci(monkeypatch, rows):
    """Run calculate_cci with a mocked Neo4j client returning *rows*."""

    class _FakeClient:
        def run(self, query, **kwargs):
            if "SET p.cci_score" in query:
                return []
            return rows

        def close(self):
            pass

    monkeypatch.setattr(cci_mod, "PatientGraphClient", lambda: _FakeClient())

    # Bypass the require_patient_in_scope guard
    monkeypatch.setattr(
        cci_mod,
        "require_patient_in_scope",
        lambda *a, **kw: None,
    )

    # CallerScope is not imported in this module; build a minimal stub
    class _FakeScope:
        email = "test@test.com"
        is_admin = True
        org_ids = []

    with mock.patch.object(cci_mod, "_coerce_scope", return_value=_FakeScope()):
        return cci_mod.calculate_cci("p-001")


def test_cci_query_filters_by_assertion(monkeypatch):
    """CCI Cypher query MUST include the assertion coalesce guard."""
    read_queries: list[dict] = []

    class _SpyClient:
        def run(self, query, **kwargs):
            if "DOCUMENTS" in query:
                read_queries.append({"query": query, "kwargs": kwargs})
                return []
            return []

        def close(self):
            pass

    monkeypatch.setattr(cci_mod, "PatientGraphClient", lambda: _SpyClient())
    monkeypatch.setattr(cci_mod, "require_patient_in_scope", lambda *a, **kw: None)

    class _FakeScope:
        email = "test@test.com"
        is_admin = True
        org_ids = []

    with mock.patch.object(cci_mod, "_coerce_scope", return_value=_FakeScope()):
        cci_mod.calculate_cci("p-001")

    assert read_queries, "expected at least one DOCUMENTS query"
    q = read_queries[0]["query"]
    kw = read_queries[0]["kwargs"]
    assert "[r:DOCUMENTS]" in q, "relationship must be aliased to r"
    assert "coalesce(r.assertion" in q, "assertion filter must use coalesce"
    assert "$assertions" in q, "assertions must be a parameter"
    assert set(kw["assertions"]) == {"present", "historical"}


def test_cci_present_condition_scores(monkeypatch):
    """A 'present' confirmed condition should increase the CCI score."""
    rows = [
        {
            "concept_name": "Diabetes without complications",
            "concept_id": "1",
            "semantic_tag": "finding",
        }
    ]
    result = _run_cci(monkeypatch, rows)
    assert result["cci_score"] == 1


def test_cci_historical_condition_scores(monkeypatch):
    """A 'historical' confirmed condition must count toward CCI (lifetime index).

    Uses HIV/AIDS (weight 6) which has no overlapping substring with other conditions.
    """
    rows = [{"concept_name": "HIV/AIDS", "concept_id": "2", "semantic_tag": "finding"}]
    result = _run_cci(monkeypatch, rows)
    assert result["cci_score"] == 6


def test_cci_absent_condition_not_returned_by_db(monkeypatch):
    """Absent conditions are excluded by Cypher; empty result -> score 0."""
    result = _run_cci(monkeypatch, [])
    assert result["cci_score"] == 0
    assert result["matched_conditions"] == []


def test_cci_multiple_conditions_sum_correctly(monkeypatch):
    """CCI score sums weights across multiple confirmed conditions."""
    rows = [
        {"concept_name": "Dementia", "concept_id": "3", "semantic_tag": "finding"},
        {"concept_name": "Renal disease", "concept_id": "4", "semantic_tag": "finding"},
    ]
    result = _run_cci(monkeypatch, rows)
    assert result["cci_score"] == 3  # 1 (dementia) + 2 (renal)


# -- Cohort filter tests ---------------------------------------------


def test_confirmed_assertions_constant():
    """The confirmed assertion set must include exactly present and historical."""
    assert _CONFIRMED_ASSERTIONS == frozenset({"present", "historical"})


def test_condition_codes_clause_includes_assertion_filter():
    """condition_codes filter must restrict to confirmed assertions."""
    f = CohortFilter(condition_codes=["12345678"])
    where, params = _build_where_clauses(f)
    assert (
        "coalesce(r.assertion" in where
    ), "assertion guard missing from condition filter"
    assert "$confirmed_assertions" in where
    assert set(params["confirmed_assertions"]) == {"present", "historical"}


def test_condition_codes_absent_assertion_excluded():
    """Cypher clause produced should NOT allow absent assertions."""
    f = CohortFilter(condition_codes=["12345678"])
    where, params = _build_where_clauses(f)
    assert "absent" not in where, "absent must not be hardcoded in clause"


def test_ever_smoker_includes_assertion_filter():
    """ever_smoker clause must apply the confirmed-assertion guard."""
    f = CohortFilter(smoking_status="ever_smoker")
    where, params = _build_where_clauses(f)
    assert "coalesce(r.assertion" in where
    assert set(params["confirmed_assertions"]) == {"present", "historical"}


def test_current_smoker_includes_assertion_filter():
    """current_smoker clause must apply the confirmed-assertion guard."""
    f = CohortFilter(smoking_status="current_smoker")
    where, params = _build_where_clauses(f)
    assert "coalesce(r.assertion" in where
    assert set(params["confirmed_assertions"]) == {"present", "historical"}


def test_confirmed_assertions_param_not_duplicated_when_both_filters_set():
    """confirmed_assertions param present when both filters are combined."""
    f = CohortFilter(
        condition_codes=["12345678"],
        smoking_status="ever_smoker",
    )
    where, params = _build_where_clauses(f)
    # params["confirmed_assertions"] must be present and valid (no key error)
    assert set(params["confirmed_assertions"]) == {"present", "historical"}


def test_no_condition_codes_no_assertion_param():
    """If no condition_codes or smoking filter, confirmed_assertions param not set."""
    f = CohortFilter(org_id=None)
    _, params = _build_where_clauses(f)
    assert "confirmed_assertions" not in params
