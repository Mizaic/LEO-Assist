"""Dashboard aggregation endpoints.

Pre-computed reads from Patient Graph for episode summaries,
cancer type distributions, and timeline views.

Org filtering uses (Patient)-[:REGISTERED_AT]->(Organization) traversal.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()


class ActionAlertRequest(BaseModel):
    actioned: bool


class EpisodeStatusRequest(BaseModel):
    status: str  # "closed" | "completed"
    reason: str


class EpisodeMergeRequest(BaseModel):
    primary_episode_id: str
    secondary_episode_ids: list[str]
    reason: str


class MilestoneUpdateRequest(BaseModel):
    milestone_type: str


class RebuildEpisodesRequest(BaseModel):
    patient_id: str
    delete_existing: bool = True


@router.post("/episodes/rebuild")
async def rebuild_patient_episodes(body: RebuildEpisodesRequest):
    """Rebuild episodes for a single patient. Runs anchor detection and episode building.
    Optionally deletes existing episodes first."""
    client = PatientGraphClient()
    try:
        if body.delete_existing:
            client.run(
                "MATCH (p:Patient)-[:HAS_EPISODE]->(ep:CancerEpisode) "
                "WHERE toString(p.id) = $pid "
                "DETACH DELETE ep",
                pid=body.patient_id,
            )

        from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
        from services.analysis_worker.app.analyzers.episode_builder import build_episodes

        anchors = detect_anchors(
            patient_id=body.patient_id,
            start_date="2000-01-01",
            end_date="2030-12-31",
            patient_client=client,
        )
        result = await build_episodes(
            patient_id=body.patient_id,
            anchors=anchors,
            patient_client=client,
        )
        return {
            "success": True,
            "patient_id": body.patient_id,
            "episodes_created": result.episodes_created,
            "episodes_completed": result.episodes_completed,
            "episodes_merged": result.episodes_merged,
            "encounters_linked": result.encounters_linked,
            "episode_ids": result.episode_ids,
        }
    finally:
        client.close()


@router.patch("/episodes/{episode_id}/status")
def close_episode(episode_id: str, body: EpisodeStatusRequest):
    """Close or archive an episode. Sets status, completed_at, completed_by."""
    if body.status not in ("closed", "completed"):
        raise HTTPException(status_code=400, detail="status must be 'closed' or 'completed'")
    client = PatientGraphClient()
    try:
        result = client.run(
            "MATCH (ep:CancerEpisode {episode_id: $eid}) "
            "SET ep.status = $status, ep.completed_at = datetime(), "
            "    ep.completed_by = 'manual', ep.agent_reasoning = $reason, "
            "    ep.status_updated_at = datetime(), ep.needs_review = false "
            "RETURN ep.episode_id AS episode_id",
            eid=episode_id,
            status=body.status,
            reason=body.reason,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Episode not found")
        return {"success": True, "episode_id": episode_id}
    finally:
        client.close()


@router.post("/episodes/merge")
def merge_episodes_endpoint(body: EpisodeMergeRequest):
    """Manually merge secondary episodes into a primary. Moves IS_PART_OF edges."""
    if not body.secondary_episode_ids:
        raise HTTPException(status_code=400, detail="secondary_episode_ids cannot be empty")
    client = PatientGraphClient()
    try:
        client.run(
            "UNWIND $sids AS sec_id "
            "MATCH (enc:Encounter)-[r:IS_PART_OF]->(sec:CancerEpisode {episode_id: sec_id}) "
            "MATCH (primary:CancerEpisode {episode_id: $pid}) "
            "MERGE (enc)-[r2:IS_PART_OF]->(primary) "
            "ON CREATE SET r2.milestone_type = r.milestone_type, "
            "              r2.agent_reasoning = 'Merged from ' + sec_id, "
            "              r2.linked_by = 'manual_merge', r2.linked_at = datetime() "
            "DELETE r",
            pid=body.primary_episode_id,
            sids=body.secondary_episode_ids,
        )
        client.run(
            "UNWIND $sids AS sec_id "
            "MATCH (ep:CancerEpisode {episode_id: sec_id}) "
            "SET ep.status = 'merged', ep.merged_into = $pid, "
            "    ep.merged_at = datetime(), ep.merge_reasoning = $reasoning, "
            "    ep.needs_review = false, ep.status_updated_at = datetime()",
            pid=body.primary_episode_id,
            sids=body.secondary_episode_ids,
            reasoning=body.reason,
        )
        client.run(
            "MATCH (primary:CancerEpisode {episode_id: $pid}) "
            "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(primary) "
            "WITH primary, min(toString(enc.date)) AS earliest, max(toString(enc.date)) AS latest "
            "SET primary.first_encounter_date = earliest, "
            "    primary.last_encounter_date = latest, "
            "    primary.merged_from = $sids, "
            "    primary.consolidation_reasoning = $reasoning, "
            "    primary.consolidated_at = datetime() "
            "RETURN primary.episode_id AS episode_id",
            pid=body.primary_episode_id,
            sids=body.secondary_episode_ids,
            reasoning=body.reason,
        )
        return {
            "success": True,
            "primary_episode_id": body.primary_episode_id,
            "merged_count": len(body.secondary_episode_ids),
        }
    finally:
        client.close()


@router.patch("/episodes/{episode_id}/milestones/{encounter_id}")
def edit_milestone(episode_id: str, encounter_id: str, body: MilestoneUpdateRequest):
    """Update the milestone type for an encounter linked to an episode."""
    valid_types = {
        "first_presentation", "presentation", "referral", "referral_sent",
        "specialist_visit", "first_clinic_visit", "clinic_visit", "first_clinic",
        "investigation", "diagnosis", "diagnosis_confirmed",
        "treatment_decision", "treatment", "treatment_started", "first_treatment",
        "related",
    }
    if body.milestone_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"milestone_type must be one of: {sorted(valid_types)}",
        )
    client = PatientGraphClient()
    try:
        result = client.run(
            "MATCH (e:Encounter {id: $eid})-[r:IS_PART_OF]->(ep:CancerEpisode {episode_id: $epid}) "
            "SET r.milestone_type = $mt, r.linked_by = 'manual_edit', r.linked_at = datetime() "
            "RETURN e.id AS encounter_id, ep.episode_id AS episode_id",
            eid=encounter_id,
            epid=episode_id,
            mt=body.milestone_type,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Encounter or episode not found")
        return {"success": True, "encounter_id": encounter_id, "milestone_type": body.milestone_type}
    finally:
        client.close()


@router.get("/episodes/summary")
def episode_summary(org_id: Optional[str] = Query(default=None)):
    """Aggregate episode counts by status and cancer type."""
    client = PatientGraphClient()
    try:
        if org_id:
            return client.run(
                "MATCH (p:Patient)-[:REGISTERED_AT]->(o:Organization {id: $org}) "
                "MATCH (p)-[:HAS_EPISODE]->(ep:CancerEpisode) "
                "RETURN ep.cancer_type AS cancer_type, ep.status AS status, count(ep) AS count "
                "ORDER BY count DESC",
                org=org_id,
            )
        return client.run(
            "MATCH (ep:CancerEpisode) "
            "RETURN ep.cancer_type AS cancer_type, ep.status AS status, count(ep) AS count "
            "ORDER BY count DESC",
        )
    finally:
        client.close()


@router.get("/episodes/timeline")
def episode_timeline(
    patient_id: Optional[str] = Query(default=None),
    org_id: Optional[str] = Query(default=None),
    include_merged: bool = Query(default=False),
):
    """Episode milestones timeline for a patient or organization.

    By default, merged episodes are excluded. Pass include_merged=true
    to show all episodes including those merged into a primary.
    """
    client = PatientGraphClient()
    merged_filter = "" if include_merged else "AND ep.status <> 'merged' "
    try:
        if patient_id:
            return client.run(
                "MATCH (p:Patient)-[:HAS_EPISODE]->(ep:CancerEpisode) "
                f"WHERE toString(p.id) = $pid {merged_filter}"
                "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
                "RETURN ep.episode_id AS episode_id, ep.cancer_type AS cancer_type, "
                "       ep.status AS status, ep.agent_confidence AS confidence, "
                "       ep.agent_reasoning AS agent_reasoning, "
                "       ep.needs_review AS needs_review, "
                "       ep.merged_into AS merged_into, "
                "       ep.merged_from AS merged_from, "
                "       ep.consolidation_reasoning AS consolidation_reasoning, "
                "       ep.referral_route AS referral_route, "
                "       ep.place_of_presentation AS place_of_presentation, "
                "       ep.safety_netting_recorded AS safety_netting_recorded, "
                "       toString(ep.referral_date) AS referral_date, "
                "       collect({encounter_id: e.id, date: toString(e.date), "
                "       milestone: r.milestone_type}) AS milestones "
                "ORDER BY ep.referral_date",
                pid=patient_id,
            )
        if org_id:
            return client.run(
                "MATCH (p:Patient)-[:REGISTERED_AT]->(o:Organization {id: $org}) "
                "MATCH (p)-[:HAS_EPISODE]->(ep:CancerEpisode) "
                f"WHERE true {merged_filter}"
                "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
                "WITH ep, p, collect({encounter_id: e.id, date: toString(e.date), "
                "     milestone: r.milestone_type}) AS milestones "
                "RETURN ep.episode_id AS episode_id, toString(p.id) AS patient_id, "
                "       ep.cancer_type AS cancer_type, ep.status AS status, "
                "       ep.agent_confidence AS confidence, "
                "       ep.agent_reasoning AS agent_reasoning, "
                "       ep.needs_review AS needs_review, "
                "       ep.merged_into AS merged_into, "
                "       ep.merged_from AS merged_from, "
                "       ep.consolidation_reasoning AS consolidation_reasoning, "
                "       toString(ep.referral_date) AS referral_date, milestones "
                "ORDER BY ep.referral_date DESC LIMIT 200",
                org=org_id,
            )
        return client.run(
            "MATCH (p:Patient)-[:HAS_EPISODE]->(ep:CancerEpisode) "
            f"WHERE true {merged_filter}"
            "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
            "WITH ep, p, collect({encounter_id: e.id, date: toString(e.date), "
            "     milestone: r.milestone_type}) AS milestones "
            "RETURN ep.episode_id AS episode_id, toString(p.id) AS patient_id, "
            "       ep.cancer_type AS cancer_type, ep.status AS status, "
            "       ep.agent_confidence AS confidence, "
            "       ep.agent_reasoning AS agent_reasoning, "
            "       ep.needs_review AS needs_review, "
            "       ep.merged_into AS merged_into, "
            "       ep.merged_from AS merged_from, "
            "       ep.consolidation_reasoning AS consolidation_reasoning, "
            "       toString(ep.referral_date) AS referral_date, milestones "
            "ORDER BY ep.referral_date DESC LIMIT 200",
        )
    finally:
        client.close()


@router.get("/css/alerts")
def css_alerts(org_id: Optional[str] = Query(default=None)):
    """List CSS alerts from the Patient Graph."""
    client = PatientGraphClient()
    try:
        org_match = (
            "MATCH (p)-[:REGISTERED_AT]->(o:Organization {id: $org}) "
            if org_id
            else ""
        )
        params = {"org": org_id} if org_id else {}
        return client.run(
            f"MATCH (p:Patient)-[:HAS_CSS_ALERT]->(a:CSSAlert) "
            f"{org_match}"
            "OPTIONAL MATCH (a)-[:FOR_EPISODE]->(ep:CancerEpisode) "
            "OPTIONAL MATCH (a)-[:TRIGGERED_AT]->(enc:Encounter) "
            "RETURN a.id AS id, a.alert_type AS type, a.rule_name AS rule_name, "
            "       a.severity AS severity, a.status AS status, "
            "       a.guideline AS guideline, a.recommendation_title AS description, "
            "       a.suggested_action AS suggested_action, "
            "       a.match_percent AS match_percent, "
            "       a.actioned AS actioned, a.needs_review AS needs_review, "
            "       toString(a.created_at) AS created_at, "
            "       ep.episode_id AS episode_id, ep.cancer_type AS cancer_type, "
            "       enc.id AS encounter_id, toString(enc.date) AS encounter_date, "
            "       p.id AS patient_id "
            "ORDER BY a.created_at DESC LIMIT 200",
            **params,
        )
    finally:
        client.close()


@router.patch("/css/alerts/{alert_id}/action")
def action_css_alert(alert_id: str, body: ActionAlertRequest):
    """Mark a CSS alert as actioned or un-actioned."""
    client = PatientGraphClient()
    try:
        result = client.run(
            "MATCH (a:CSSAlert {id: $aid}) "
            "SET a.actioned = $actioned "
            "RETURN a.id AS id",
            aid=alert_id,
            actioned=body.actioned,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"success": True}
    finally:
        client.close()
