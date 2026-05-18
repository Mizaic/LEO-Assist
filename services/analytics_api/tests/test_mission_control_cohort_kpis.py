"""VT-LEO-AI-206 -- Mission Control KPI unit clarity + cohort denominator.

Backend verification covering DI-LEO-AI-214:

  TC-001  _kpis_cypher exposes BOTH episode and patient counts for
          confirmed_cancer (so the UI can show "patients" in the
          headline and "pathways" as the sub-line)
  TC-002  _kpis_cypher exposes BOTH episode and patient counts for
          pathway_closures (same reason)
  TC-003  _cohort_denominator_cypher returns the four cohort fields
          (total + 3 excluded buckets) and is scoped by org/scope ONLY,
          NOT by date / pathway / cancer-type filters
  TC-004  GET /mission-control/kpis returns a "cohort" block alongside
          the in-view counts so the UI can render "Showing X of Y"
  TC-005  When the cohort query returns no rows, the endpoint still
          returns a zero-filled cohort block (no KeyError)
"""

from __future__ import annotations

import pytest

from libs.auth.org_scope import CallerScope
from services.analytics_api.app.routers import mission_control as mc
from services.analytics_api.app.routers.mission_control import (
    _cohort_denominator_cypher,
    _kpis_cypher,
)


BASE = (
    "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "WHERE NOT ep.status IN ['merged', 'closed_phantom'] "
    "AND ep.referral_date >= '2024-01-01' "
    "AND ep.referral_date <= '2025-12-31' "
)


def _admin_scope() -> CallerScope:
    return CallerScope(
        email="qa@example.com",
        is_admin=True,
        org_ids=[],
        scope_type="alliance",
        primary_org_id=None,
    )


def _gp_scope() -> CallerScope:
    return CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )


# ----- TC-001 --------------------------------------------------------------


def test_kpis_cypher_exposes_confirmed_cancer_patient_count():
    """VT-206-TC-001: confirmed_cancer_patients counts DISTINCT p, not ep."""
    q, _ = _kpis_cypher(BASE, {})
    assert "confirmed_cancer_patients" in q
    # Patient-equivalent must group by p (DISTINCT p), not by ep.
    assert "THEN p END) " in q
    assert "AS confirmed_cancer_patients" in q
    # Existing episode count is preserved for backward compatibility.
    assert "AS confirmed_cancer," in q


# ----- TC-002 --------------------------------------------------------------


def test_kpis_cypher_exposes_pathway_closure_patient_count():
    """VT-206-TC-002: pathway_closure_patients counts DISTINCT p, not ep."""
    q, _ = _kpis_cypher(BASE, {})
    assert "pathway_closure_patients" in q
    assert "AS pathway_closure_patients" in q
    assert "AS pathway_closures," in q
    assert "median_benign_interval_days" in q


# ----- TC-003 --------------------------------------------------------------


def test_cohort_denominator_cypher_returns_four_fields():
    """VT-206-TC-003: cohort denominator query exposes total + 3 buckets."""
    q, _ = _cohort_denominator_cypher(
        org_id=None,
        scope=_admin_scope(),
        date_from="2024-01-01",
        date_to="2025-12-31",
    )
    assert "cohort_total_patients" in q
    assert "excluded_no_pathway" in q
    assert "excluded_missing_referral_date" in q
    assert "excluded_outside_window" in q


def test_cohort_denominator_cypher_admin_scope_uses_unfiltered_match():
    """Admin scope without org_id matches all Patient nodes."""
    q, params = _cohort_denominator_cypher(
        org_id=None,
        scope=_admin_scope(),
        date_from=None,
        date_to=None,
    )
    assert "MATCH (p:Patient)" in q
    assert "Organization" not in q
    assert params == {}


def test_cohort_denominator_cypher_org_scope_uses_org_param():
    """GP scope with primary_org_id binds the org filter on $org param."""
    _, params = _cohort_denominator_cypher(
        org_id=None,
        scope=_gp_scope(),
        date_from="2024-01-01",
        date_to="2025-12-31",
    )
    assert params.get("org") == "org-1"


def test_cohort_denominator_cypher_ignores_pathway_and_cancer_type_filters():
    """Cohort denominator MUST NOT apply pathway/cancer-type/closure filters.

    The denominator answers "how many patients exist behind the filter",
    so it has to ignore everything except scope + date window.
    """
    q, _ = _cohort_denominator_cypher(
        org_id=None,
        scope=_admin_scope(),
        date_from="2024-01-01",
        date_to="2025-12-31",
    )
    assert "cancer_type" not in q
    assert "closure_reason" not in q
    assert "reviewed_at" not in q


# ----- TC-004 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_kpis_endpoint_returns_cohort_block(monkeypatch):
    """VT-206-TC-004: /mission-control/kpis surfaces a cohort denominator."""

    class _FakeClient:
        def run(self, query, **_kwargs):
            if "cohort_total_patients" in query:
                return [
                    {
                        "cohort_total_patients": 107,
                        "excluded_total": 18,
                        "excluded_no_pathway": 8,
                        "excluded_missing_referral_date": 7,
                        "excluded_outside_window": 3,
                    }
                ]
            return [
                {
                    "total_patients": 89,
                    "confirmed_cancer": 54,
                    "confirmed_cancer_patients": 44,
                    "pathway_closures": 76,
                    "pathway_closure_patients": 60,
                    "median_diagnostic_interval_days": 28.0,
                    "safety_netting_rate": 0.85,
                    "needs_review_count": 5,
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(mc, "PatientGraphClient", _FakeClient)

    result = mc.get_mission_control_kpis(
        org_id=None,
        date_from="2024-01-01",
        date_to="2025-12-31",
        pathway_filter="all",
        cancer_types=None,
        closure_reasons=None,
        review_status="all",
        patient_id=None,
        scope=_admin_scope(),
    )

    assert result["total_patients"] == 89
    assert result["confirmed_cancer"] == 54
    assert result["confirmed_cancer_patients"] == 44
    assert result["pathway_closures"] == 76
    assert result["pathway_closure_patients"] == 60
    assert result["cohort"] == {
        "total_patients": 107,
        "excluded_total": 18,
        "excluded_no_pathway": 8,
        "excluded_missing_referral_date": 7,
        "excluded_outside_window": 3,
    }


# ----- TC-005 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_kpis_endpoint_returns_zeroed_cohort_when_query_empty(monkeypatch):
    """VT-206-TC-005: empty Cypher result returns zero cohort, not KeyError."""

    class _FakeClient:
        def run(self, query, **_kwargs):
            return []

        def close(self):
            return None

    monkeypatch.setattr(mc, "PatientGraphClient", _FakeClient)

    result = mc.get_mission_control_kpis(
        org_id=None,
        date_from="2024-01-01",
        date_to="2025-12-31",
        pathway_filter="all",
        cancer_types=None,
        closure_reasons=None,
        review_status="all",
        patient_id=None,
        scope=_admin_scope(),
    )

    assert result["confirmed_cancer_patients"] == 0
    assert result["pathway_closure_patients"] == 0
    assert result["cohort"] == {
        "total_patients": 0,
        "excluded_total": 0,
        "excluded_no_pathway": 0,
        "excluded_missing_referral_date": 0,
        "excluded_outside_window": 0,
    }
