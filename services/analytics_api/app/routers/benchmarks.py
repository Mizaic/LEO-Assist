"""Benchmark comparison endpoints.

Provides organization-level benchmarks and peer comparisons
for KPI metrics from cancer episodes.

Org filtering uses (Patient)-[:REGISTERED_AT]->(Organization) traversal.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()


@router.get("/benchmarks/kpis")
def kpi_benchmarks(org_id: Optional[str] = Query(default=None)):
    """Aggregate KPI metrics across episodes for benchmarking."""
    client = PatientGraphClient()
    try:
        if org_id:
            return client.run(
                "MATCH (p:Patient)-[:REGISTERED_AT]->(o:Organization {id: $org}) "
                "MATCH (p)-[:HAS_EPISODE]->(ep:CancerEpisode) "
                "WITH ep WHERE ep.kpi_days_referral_to_diagnosis IS NOT NULL "
                "RETURN "
                "  avg(ep.kpi_days_presentation_to_referral) AS avg_days_to_referral, "
                "  avg(ep.kpi_days_referral_to_diagnosis) AS avg_days_to_diagnosis, "
                "  avg(ep.kpi_days_diagnosis_to_treatment) AS avg_days_to_treatment, "
                "  avg(ep.kpi_consultations_before_referral) AS avg_consultations, "
                "  count(ep) AS episode_count",
                org=org_id,
            )
        return client.run(
            "MATCH (ep:CancerEpisode) "
            "WITH ep WHERE ep.kpi_days_referral_to_diagnosis IS NOT NULL "
            "RETURN "
            "  avg(ep.kpi_days_presentation_to_referral) AS avg_days_to_referral, "
            "  avg(ep.kpi_days_referral_to_diagnosis) AS avg_days_to_diagnosis, "
            "  avg(ep.kpi_days_diagnosis_to_treatment) AS avg_days_to_treatment, "
            "  avg(ep.kpi_consultations_before_referral) AS avg_consultations, "
            "  count(ep) AS episode_count",
        )
    finally:
        client.close()


@router.get("/benchmarks/comparison")
def peer_comparison(
    org_id: str = Query(...),
    metric: str = Query(default="kpi_days_referral_to_diagnosis"),
):
    """Compare an organization's metric against all organizations."""
    client = PatientGraphClient()
    try:
        return client.run(
            "MATCH (p:Patient)-[:REGISTERED_AT]->(o:Organization) "
            "MATCH (p)-[:HAS_EPISODE]->(ep:CancerEpisode) "
            "WHERE ep[$metric] IS NOT NULL "
            "WITH o.id AS org, o.name AS org_name, avg(ep[$metric]) AS avg_val, count(ep) AS cnt "
            "RETURN org, org_name, avg_val, cnt, "
            "  CASE WHEN org = $org_id THEN true ELSE false END AS is_self "
            "ORDER BY avg_val",
            metric=metric, org_id=org_id,
        )
    finally:
        client.close()


@router.get("/benchmarks/trends")
def kpi_trends(
    org_id: Optional[str] = Query(default=None),
    metric: str = Query(default="kpi_days_referral_to_diagnosis"),
):
    """Monthly trend data for a KPI metric."""
    client = PatientGraphClient()
    try:
        if org_id:
            return client.run(
                "MATCH (p:Patient)-[:REGISTERED_AT]->(o:Organization {id: $org}) "
                "MATCH (p)-[:HAS_EPISODE]->(ep:CancerEpisode) "
                "WHERE ep[$metric] IS NOT NULL AND ep.referral_date IS NOT NULL "
                "WITH substring(ep.referral_date, 0, 7) AS month, "
                "     avg(ep[$metric]) AS avg_val, count(ep) AS cnt "
                "RETURN month, avg_val, cnt ORDER BY month",
                org=org_id, metric=metric,
            )
        return client.run(
            "MATCH (ep:CancerEpisode) "
            "WHERE ep[$metric] IS NOT NULL AND ep.referral_date IS NOT NULL "
            "WITH substring(ep.referral_date, 0, 7) AS month, "
            "     avg(ep[$metric]) AS avg_val, count(ep) AS cnt "
            "RETURN month, avg_val, cnt ORDER BY month",
            metric=metric,
        )
    finally:
        client.close()
