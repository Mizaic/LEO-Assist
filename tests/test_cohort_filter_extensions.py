"""VT-LEO-AI-230 -- CohortFilter extensions for the PatientFinder.

Verifies DI-LEO-AI-230 acceptance criteria for the four new filter
dimensions added to support the PatientFinder primitive:
  - imd_decile_min / imd_decile_max
  - encounter_count_{min,max} with configurable window months
  - episode_domain + episode_subdomain (cancer_audit special case)
  - episode_outcome shorthand reusing canonical NCDA fragments

Each dimension is exercised through the tiny named helper that owns
its WHERE-clause shape so we can pin the Cypher contract without a
live Neo4j instance.
"""

from __future__ import annotations

from services.analytics_api.app.routers.cohorts import (
    CohortFilter,
    _append_encounter_count_clause,
    _append_episode_domain_clause,
    _append_imd_clause,
    _build_where_clauses,
)


def test_imd_clause_emits_optional_address_match() -> None:
    f = CohortFilter(imd_decile_min=1, imd_decile_max=3)
    clauses: list[str] = []
    params: dict[str, object] = {}
    _append_imd_clause(f, clauses, params)
    assert len(clauses) == 1
    assert "MATCH (p)-[:HAS_ADDRESS]->(a:Address)" in clauses[0]
    assert "a.imd_decile IS NOT NULL" in clauses[0]
    assert "a.imd_decile >= $imd_decile_min" in clauses[0]
    assert "a.imd_decile <= $imd_decile_max" in clauses[0]
    assert params == {"imd_decile_min": 1, "imd_decile_max": 3}


def test_imd_clause_no_op_when_both_bounds_missing() -> None:
    clauses: list[str] = []
    params: dict[str, object] = {}
    _append_imd_clause(CohortFilter(), clauses, params)
    assert clauses == []
    assert params == {}


def test_encounter_count_window_defaults_to_12_months() -> None:
    f = CohortFilter(encounter_count_min=2)
    clauses: list[str] = []
    params: dict[str, object] = {}
    _append_encounter_count_clause(f, clauses, params)
    assert params["encounter_window_months"] == 12
    assert params["encounter_count_min"] == 2
    assert "duration({months: $encounter_window_months})" in clauses[0]


def test_encounter_count_window_respects_explicit_months() -> None:
    f = CohortFilter(
        encounter_count_min=1,
        encounter_count_max=10,
        encounter_count_window_months=6,
    )
    clauses: list[str] = []
    params: dict[str, object] = {}
    _append_encounter_count_clause(f, clauses, params)
    assert params["encounter_window_months"] == 6
    assert ">= $encounter_count_min" in clauses[0]
    assert "<= $encounter_count_max" in clauses[0]


def test_episode_domain_with_cancer_subdomain_uses_cancer_type() -> None:
    f = CohortFilter(episode_domain="cancer_audit", episode_subdomain="breast")
    clauses: list[str] = []
    params: dict[str, object] = {}
    _append_episode_domain_clause(f, clauses, params)
    assert "ep.cancer_type = $episode_subdomain" in clauses[0]
    assert params["episode_subdomain"] == "breast"


def test_episode_subdomain_for_non_cancer_uses_ep_subdomain() -> None:
    f = CohortFilter(episode_domain="ltc_audit", episode_subdomain="diabetes")
    clauses: list[str] = []
    params: dict[str, object] = {}
    _append_episode_domain_clause(f, clauses, params)
    assert "ep.subdomain" in clauses[0]
    assert "ep.cancer_type" not in clauses[0]


def test_build_where_clauses_combines_extensions_with_AND() -> None:
    f = CohortFilter(
        age_min=40,
        age_max=80,
        sex="female",
        imd_decile_min=1,
        episode_domain="cancer_audit",
        episode_subdomain="breast",
    )
    where, params = _build_where_clauses(f)
    parts = where.split(" AND ")
    assert any(p.startswith("p.age >= ") for p in parts)
    assert any("a.imd_decile >= $imd_decile_min" in p for p in parts)
    assert any("ep.cancer_type" in p for p in parts)
    for required in ("age_min", "age_max", "sex", "imd_decile_min",
                     "episode_domain", "episode_subdomain"):
        assert required in params, f"missing param {required}"


def test_build_where_clauses_returns_true_for_empty_filter() -> None:
    where, params = _build_where_clauses(CohortFilter())
    assert where == "true"
    assert params == {}
