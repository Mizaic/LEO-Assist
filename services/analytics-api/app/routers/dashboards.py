"""Dashboard aggregation endpoints.

Pre-computed reads from Patient Graph for episode summaries,
cancer type distributions, and timeline views.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()


@router.get("/episodes/summary")
def episode_summary(org_id: Optional[str] = Query(default=None)):
    """Aggregate episode counts by status and cancer type."""
    client = PatientGraphClient()
    try:
        tenant_filter = "WHERE ep.tenantId = $org" if org_id else ""
        params = {"org": org_id} if org_id else {}
        return client.run(
            f"MATCH (ep:CancerEpisode) {tenant_filter} "
            "RETURN ep.cancer_type AS cancer_type, ep.status AS status, count(ep) AS count "
            "ORDER BY count DESC",
            **params,
        )
    finally:
        client.close()


@router.get("/episodes/timeline")
def episode_timeline(
    patient_id: Optional[str] = Query(default=None),
    org_id: Optional[str] = Query(default=None),
):
    """Episode milestones timeline for a patient or organization."""
    client = PatientGraphClient()
    try:
        if patient_id:
            return client.run(
                "MATCH (ep:CancerEpisode {patient_id: $pid}) "
                "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
                "RETURN ep.episode_id AS episode_id, ep.cancer_type AS cancer_type, "
                "       ep.status AS status, collect({encounter_id: e.id, date: toString(e.date), "
                "       milestone: r.milestone_type}) AS milestones "
                "ORDER BY ep.referral_date",
                pid=patient_id,
            )
        return client.run(
            "MATCH (ep:CancerEpisode) WHERE $org IS NULL OR ep.tenantId = $org "
            "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id, "
            "       ep.cancer_type AS cancer_type, ep.status AS status, "
            "       ep.referral_date AS referral_date "
            "ORDER BY ep.referral_date DESC LIMIT 100",
            org=org_id,
        )
    finally:
        client.close()


@router.get("/css/alerts")
def css_alerts(org_id: Optional[str] = Query(default=None)):
    """List CSS alerts from the Patient Graph."""
    client = PatientGraphClient()
    try:
        return client.run(
            "MATCH (a:CSSAlert) WHERE $org IS NULL OR a.tenantId = $org "
            "RETURN a.episode_id AS episode_id, a.type AS type, a.severity AS severity, "
            "       a.description AS description "
            "ORDER BY a.created_at DESC LIMIT 200",
            org=org_id,
        )
    finally:
        client.close()
