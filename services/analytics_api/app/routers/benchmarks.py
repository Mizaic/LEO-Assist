"""Benchmark comparison endpoints.

Provides organization-level benchmarks and peer comparisons
for KPI metrics from cancer episodes.

Org filtering traverses (Patient)-[:HAS_GENERAL_PRACTITIONER]->(GP)
and supports GP / ICB / CancerAlliance scope levels via COMMISSIONED_BY
and PART_OF_ALLIANCE relationships.

KPI metrics are computed inline from IS_PART_OF milestone relationships
(referral_date and first_presentation_date on EpisodeOfCare, plus
diagnosis/treatment encounter dates from milestones).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from libs.auth.org_scope import CallerScope, ORG_PATIENT_FILTER, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()

# Cypher fragment that scopes patients to an org at any hierarchy level.
# Variables introduced: _scope, gp  (p must already be in scope or follow).
_ORG_PATIENT_MATCH = (
    "MATCH (_scope:Organization {{id: ${p}}}) "
    "MATCH (p:Patient) "
    "OPTIONAL MATCH (p)-[:REGISTERED_AT]->(org:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
    "WHERE (org.id = ${p}) OR (gp.id = ${p}) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
    "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
    "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
)


def _coerce_scope(scope: CallerScope | object) -> CallerScope:
    if isinstance(scope, CallerScope):
        return scope
    return CallerScope(email="test@local", is_admin=True, org_ids=[])


def _episode_base(org_id: Optional[str], scope: CallerScope) -> tuple[str, dict]:
    """Return (cypher_prefix, params) for scoped or unscoped episode matching."""
    effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
    if effective_org:
        return _ORG_PATIENT_MATCH.format(p="org"), {"org": effective_org}
    if scope.is_admin:
        return "MATCH (ep:EpisodeOfCare) ", {}
    return (
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        f"WHERE {ORG_PATIENT_FILTER} ",
        scope.to_query_params(),
    )


@router.get("/benchmarks/kpis")
def kpi_benchmarks(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
):
    """Aggregate KPI metrics across episodes, computed from IS_PART_OF milestones."""
    scope = _coerce_scope(scope)
    client = PatientGraphClient()
    base, params = _episode_base(org_id, scope)
    try:
        return client.run(
            f"{base}"
            "WHERE ep.referral_date IS NOT NULL "
            "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
            "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
            "OPTIONAL MATCH (treat_enc:Encounter)-[tr:IS_PART_OF]->(ep) "
            "  WHERE tr.milestone_type IN ['treatment', 'treatment_started', 'first_treatment'] "
            "WITH ep, min(toString(diag_enc.date)) AS diag_date, min(toString(treat_enc.date)) AS treat_date "
            "WITH ep, treat_date, "
            "  CASE "
            "    WHEN diag_date IS NOT NULL THEN diag_date "
            "    WHEN ep.inferred_outcome = 'cancer' AND ep.inferred_outcome_date IS NOT NULL "
            "      THEN ep.inferred_outcome_date "
            "    ELSE null "
            "  END AS effective_diag_date, "
            "  (diag_date IS NULL AND ep.inferred_outcome = 'cancer' "
            "   AND ep.inferred_outcome_date IS NOT NULL) AS diag_is_inferred "
            "RETURN "
            "  avg(CASE WHEN ep.first_presentation_date IS NOT NULL "
            "      THEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days "
            "      ELSE null END) AS avg_days_to_referral, "
            "  avg(CASE WHEN effective_diag_date IS NOT NULL "
            "      THEN duration.inDays(date(toString(ep.referral_date)), date(effective_diag_date)).days "
            "      ELSE null END) AS avg_days_to_diagnosis, "
            "  avg(CASE WHEN effective_diag_date IS NOT NULL AND treat_date IS NOT NULL "
            "      THEN duration.inDays(date(effective_diag_date), date(treat_date)).days "
            "      ELSE null END) AS avg_days_to_treatment, "
            "  null AS avg_consultations, "
            "  count(ep) AS episode_count, "
            "  sum(CASE WHEN diag_is_inferred THEN 1 ELSE 0 END) AS inferred_diagnosis_count",
            **params,
        )
    finally:
        client.close()


@router.get("/benchmarks/comparison")
def peer_comparison(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: str = Query(...),
    metric: str = Query(default="avg_days_to_diagnosis"),
):
    """Compare an organization's KPI against all organizations.

    metric must be one of: avg_days_to_referral | avg_days_to_diagnosis |
    avg_days_to_treatment.
    """
    scope = _coerce_scope(scope)
    _ALLOWED = {"avg_days_to_referral", "avg_days_to_diagnosis", "avg_days_to_treatment"}
    if metric not in _ALLOWED:
        metric = "avg_days_to_diagnosis"

    if not scope.is_admin and org_id not in scope.org_ids:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    client = PatientGraphClient()
    try:
        return client.run(
            "MATCH (p:Patient)-[:REGISTERED_AT]->(org:Organization) "
            "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:GPPractice) "
            "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE ep.referral_date IS NOT NULL "
            "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
            "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
            "OPTIONAL MATCH (treat_enc:Encounter)-[tr:IS_PART_OF]->(ep) "
            "  WHERE tr.milestone_type IN ['treatment', 'treatment_started', 'first_treatment'] "
            "WITH gp, ep, min(toString(diag_enc.date)) AS diag_date, min(toString(treat_enc.date)) AS treat_date "
            "WITH gp, "
            "  CASE WHEN ep.first_presentation_date IS NOT NULL "
            "       THEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days "
            "       ELSE null END AS days_to_referral, "
            "  CASE WHEN diag_date IS NOT NULL "
            "       THEN duration.inDays(date(toString(ep.referral_date)), date(diag_date)).days "
            "       ELSE null END AS days_to_diagnosis, "
            "  CASE WHEN diag_date IS NOT NULL AND treat_date IS NOT NULL "
            "       THEN duration.inDays(date(diag_date), date(treat_date)).days "
            "       ELSE null END AS days_to_treatment "
            "WITH coalesce(org.id, gp.id) AS org, gp.name AS org_name, "
            "  avg(days_to_referral) AS avg_days_to_referral, "
            "  avg(days_to_diagnosis) AS avg_days_to_diagnosis, "
            "  avg(days_to_treatment) AS avg_days_to_treatment, "
            "  count(*) AS cnt "
            "RETURN org, org_name, "
            "  CASE $metric "
            "    WHEN 'avg_days_to_referral' THEN avg_days_to_referral "
            "    WHEN 'avg_days_to_treatment' THEN avg_days_to_treatment "
            "    ELSE avg_days_to_diagnosis END AS avg_val, "
            "  cnt, "
            "  CASE WHEN org = $org_id THEN true ELSE false END AS is_self "
            "ORDER BY avg_val",
            metric=metric, org_id=org_id,
        )
    finally:
        client.close()


@router.get("/benchmarks/trends")
def kpi_trends(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    metric: str = Query(default="avg_days_to_diagnosis"),
):
    """Monthly trend data for a KPI metric."""
    scope = _coerce_scope(scope)
    _ALLOWED = {"avg_days_to_referral", "avg_days_to_diagnosis", "avg_days_to_treatment"}
    if metric not in _ALLOWED:
        metric = "avg_days_to_diagnosis"

    client = PatientGraphClient()
    base, params = _episode_base(org_id, scope)
    params["metric"] = metric
    try:
        return client.run(
            f"{base}"
            "WHERE ep.referral_date IS NOT NULL "
            "OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep) "
            "  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
            "OPTIONAL MATCH (treat_enc:Encounter)-[tr:IS_PART_OF]->(ep) "
            "  WHERE tr.milestone_type IN ['treatment', 'treatment_started', 'first_treatment'] "
            "WITH ep, min(toString(diag_enc.date)) AS diag_date, min(toString(treat_enc.date)) AS treat_date, "
            "     substring(toString(ep.referral_date), 0, 7) AS month "
            "WITH month, "
            "  avg(CASE WHEN ep.first_presentation_date IS NOT NULL "
            "      THEN duration.inDays(date(ep.first_presentation_date), date(toString(ep.referral_date))).days "
            "      ELSE null END) AS avg_days_to_referral, "
            "  avg(CASE WHEN diag_date IS NOT NULL "
            "      THEN duration.inDays(date(toString(ep.referral_date)), date(diag_date)).days "
            "      ELSE null END) AS avg_days_to_diagnosis, "
            "  avg(CASE WHEN diag_date IS NOT NULL AND treat_date IS NOT NULL "
            "      THEN duration.inDays(date(diag_date), date(treat_date)).days "
            "      ELSE null END) AS avg_days_to_treatment, "
            "  count(*) AS cnt "
            "RETURN month, "
            "  CASE $metric "
            "    WHEN 'avg_days_to_referral' THEN avg_days_to_referral "
            "    WHEN 'avg_days_to_treatment' THEN avg_days_to_treatment "
            "    ELSE avg_days_to_diagnosis END AS avg_val, "
            "  cnt "
            "ORDER BY month",
            **params,
        )
    finally:
        client.close()
