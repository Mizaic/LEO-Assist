"""Dashboard aggregation endpoints.

Pre-computed reads from Patient Graph for episode summaries,
cancer type distributions, and timeline views.

Org filtering traverses (Patient)-[:HAS_GENERAL_PRACTITIONER]->(GP)
and supports GP / ICB / CancerAlliance scope levels via COMMISSIONED_BY
and PART_OF_ALLIANCE relationships.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, ORG_PATIENT_FILTER, get_caller_scope
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


def _coerce_scope(scope: CallerScope | object) -> CallerScope:
    if isinstance(scope, CallerScope):
        return scope
    return CallerScope(email="test@local", is_admin=True, org_ids=[])


def _scope_filter(scope: CallerScope) -> tuple[str, dict]:
    """Return (WHERE fragment, params) to restrict patient queries by caller scope.

    Admins get an empty filter (see everything).
    Scoped users get an EXISTS sub-query restricting patients to their org hierarchy.
    """
    if scope.is_admin:
        return "", {}
    return (
        f"AND {ORG_PATIENT_FILTER} ",
        scope.to_query_params(),
    )


@router.post("/episodes/rebuild")
async def rebuild_patient_episodes(
    body: RebuildEpisodesRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Rebuild episodes for a single patient. Runs anchor detection and episode building.
    Optionally deletes existing episodes first."""
    scope = _coerce_scope(scope)
    from libs.auth.org_scope import require_patient_in_scope

    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, body.patient_id)
        if body.delete_existing:
            client.run(
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
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
def close_episode(
    episode_id: str,
    body: EpisodeStatusRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Close or archive an episode. Sets status, completed_at, completed_by."""
    scope = _coerce_scope(scope)
    if body.status not in ("closed", "completed"):
        raise HTTPException(status_code=400, detail="status must be 'closed' or 'completed'")
    client = PatientGraphClient()
    try:
        if not scope.is_admin:
            owner = client.run(
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare {episode_id: $eid}) "
                "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "RETURN gp.id AS gp_id",
                eid=episode_id,
            )
            if not owner or owner[0].get("gp_id") not in scope.org_ids:
                raise HTTPException(status_code=404, detail="Episode not found")
        result = client.run(
            "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
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
def merge_episodes_endpoint(
    body: EpisodeMergeRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Manually merge secondary episodes into a primary. Moves IS_PART_OF edges."""
    scope = _coerce_scope(scope)
    if not body.secondary_episode_ids:
        raise HTTPException(status_code=400, detail="secondary_episode_ids cannot be empty")
    client = PatientGraphClient()
    try:
        if not scope.is_admin:
            all_ep_ids = [body.primary_episode_id] + body.secondary_episode_ids
            check = client.run(
                "UNWIND $eids AS eid "
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare {episode_id: eid}) "
                "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "RETURN DISTINCT gp.id AS gp_id",
                eids=all_ep_ids,
            )
            for row in check:
                if row.get("gp_id") not in scope.org_ids:
                    raise HTTPException(status_code=403, detail="Not authorized to merge these episodes")
        client.run(
            "UNWIND $sids AS sec_id "
            "MATCH (enc:Encounter)-[r:IS_PART_OF]->(sec:EpisodeOfCare {episode_id: sec_id}) "
            "MATCH (primary:EpisodeOfCare {episode_id: $pid}) "
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
            "MATCH (ep:EpisodeOfCare {episode_id: sec_id}) "
            "SET ep.status = 'merged', ep.merged_into = $pid, "
            "    ep.merged_at = datetime(), ep.merge_reasoning = $reasoning, "
            "    ep.needs_review = false, ep.status_updated_at = datetime()",
            pid=body.primary_episode_id,
            sids=body.secondary_episode_ids,
            reasoning=body.reason,
        )
        client.run(
            "MATCH (primary:EpisodeOfCare {episode_id: $pid}) "
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
def edit_milestone(
    episode_id: str,
    encounter_id: str,
    body: MilestoneUpdateRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Update the milestone type for an encounter linked to an episode."""
    scope = _coerce_scope(scope)
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
        if not scope.is_admin:
            owner = client.run(
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare {episode_id: $epid}) "
                "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "RETURN gp.id AS gp_id",
                epid=episode_id,
            )
            if not owner or owner[0].get("gp_id") not in scope.org_ids:
                raise HTTPException(status_code=404, detail="Episode not found")
        result = client.run(
            "MATCH (e:Encounter {id: $eid})-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $epid}) "
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


def _date_where(date_from: Optional[str], date_to: Optional[str], alias: str = "ep") -> tuple[str, dict]:
    """Return (extra WHERE fragment, extra params) for referral_date filtering."""
    clauses, params = [], {}
    if date_from:
        clauses.append(f"{alias}.referral_date >= date($date_from)")
        params["date_from"] = date_from
    if date_to:
        clauses.append(f"{alias}.referral_date <= date($date_to)")
        params["date_to"] = date_to
    fragment = (" AND " + " AND ".join(clauses)) if clauses else ""
    return fragment, params


@router.get("/episodes/summary")
def episode_summary(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
):
    """Aggregate episode counts by status and cancer type, with optional date range filter."""
    scope = _coerce_scope(scope)
    client = PatientGraphClient()
    date_frag, date_params = _date_where(date_from, date_to)
    scope_frag, scope_params = _scope_filter(scope)
    try:
        effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
        if effective_org:
            return client.run(
                "MATCH (_scope:Organization {id: $org}) "
                "MATCH (p:Patient) "
                "OPTIONAL MATCH (p)-[:REGISTERED_AT]->(orgNode:Organization) "
                "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "WHERE (orgNode.id = $org) OR (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
                "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
                "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                f"WHERE ep.referral_date IS NOT NULL{date_frag} "
                "RETURN ep.cancer_type AS condition_type, ep.status AS status, count(ep) AS count "
                "ORDER BY count DESC",
                org=effective_org, **date_params,
            )
        return client.run(
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            f"WHERE ep.referral_date IS NOT NULL {scope_frag}{date_frag} "
            "RETURN ep.cancer_type AS condition_type, ep.status AS status, count(ep) AS count "
            "ORDER BY count DESC",
            **date_params, **scope_params,
        )
    finally:
        client.close()


@router.get("/episodes/diagnosed")
def episode_diagnosed(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
):
    """Confirmed diagnoses grouped by cancer type, with optional date range and org filters."""
    scope = _coerce_scope(scope)
    client = PatientGraphClient()
    date_frag, date_params = _date_where(date_from, date_to)
    scope_frag, scope_params = _scope_filter(scope)
    try:
        effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
        if effective_org:
            return client.run(
                "MATCH (_scope:Organization {id: $org}) "
                "MATCH (p:Patient) "
                "OPTIONAL MATCH (p)-[:REGISTERED_AT]->(orgNode:Organization) "
                "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "WHERE (orgNode.id = $org) OR (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
                "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
                "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                f"WHERE ep.status = 'confirmed' AND ep.referral_date IS NOT NULL{date_frag} "
                "RETURN ep.cancer_type AS cancer_type, count(ep) AS count "
                "ORDER BY count DESC",
                org=effective_org, **date_params,
            )
        return client.run(
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            f"WHERE ep.status = 'confirmed' AND ep.referral_date IS NOT NULL {scope_frag}{date_frag} "
            "RETURN ep.cancer_type AS cancer_type, count(ep) AS count "
            "ORDER BY count DESC",
            **date_params, **scope_params,
        )
    finally:
        client.close()


@router.get("/episodes/timeline")
def episode_timeline(
    scope: CallerScope = Depends(get_caller_scope),
    patient_id: Optional[str] = Query(default=None),
    org_id: Optional[str] = Query(default=None),
    include_merged: bool = Query(default=False),
):
    """Episode milestones timeline for a patient or organization.

    By default, merged episodes are excluded. Pass include_merged=true
    to show all episodes including those merged into a primary.
    """
    scope = _coerce_scope(scope)
    from libs.auth.org_scope import require_patient_in_scope

    client = PatientGraphClient()
    merged_filter = "" if include_merged else "AND ep.status <> 'merged' "
    scope_frag, scope_params = _scope_filter(scope)
    try:
        if patient_id:
            require_patient_in_scope(client, scope, patient_id)
            return client.run(
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                f"WHERE toString(p.id) = $pid {merged_filter}"
                "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
                "RETURN ep.episode_id AS episode_id, ep.cancer_type AS condition_type, "
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
        effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
        if effective_org:
            return client.run(
                "MATCH (_scope:Organization {id: $org}) "
                "MATCH (p:Patient) "
                "OPTIONAL MATCH (p)-[:REGISTERED_AT]->(orgNode:Organization) "
                "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "WHERE (orgNode.id = $org) OR (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
                "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
                "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                f"WHERE true {merged_filter}"
                "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
                "WITH ep, p, collect({encounter_id: e.id, date: toString(e.date), "
                "     milestone: r.milestone_type}) AS milestones "
                "RETURN ep.episode_id AS episode_id, toString(p.id) AS patient_id, "
                "       ep.cancer_type AS condition_type, ep.status AS status, "
                "       ep.agent_confidence AS confidence, "
                "       ep.agent_reasoning AS agent_reasoning, "
                "       ep.needs_review AS needs_review, "
                "       ep.merged_into AS merged_into, "
                "       ep.merged_from AS merged_from, "
                "       ep.consolidation_reasoning AS consolidation_reasoning, "
                "       toString(ep.referral_date) AS referral_date, milestones "
                "ORDER BY ep.referral_date DESC LIMIT 200",
                org=effective_org,
            )
        return client.run(
            "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            f"WHERE true {merged_filter}{scope_frag}"
            "OPTIONAL MATCH (e:Encounter)-[r:IS_PART_OF]->(ep) "
            "WITH ep, p, collect({encounter_id: e.id, date: toString(e.date), "
            "     milestone: r.milestone_type}) AS milestones "
            "RETURN ep.episode_id AS episode_id, toString(p.id) AS patient_id, "
            "       ep.cancer_type AS condition_type, ep.status AS status, "
            "       ep.agent_confidence AS confidence, "
            "       ep.agent_reasoning AS agent_reasoning, "
            "       ep.needs_review AS needs_review, "
            "       ep.merged_into AS merged_into, "
            "       ep.merged_from AS merged_from, "
            "       ep.consolidation_reasoning AS consolidation_reasoning, "
            "       toString(ep.referral_date) AS referral_date, milestones "
            "ORDER BY ep.referral_date DESC LIMIT 200",
            **scope_params,
        )
    finally:
        client.close()


@router.get("/safety-netting/alerts")
def safety_net_alerts(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
):
    """List safety-net alerts from the Patient Graph."""
    scope = _coerce_scope(scope)
    client = PatientGraphClient()
    scope_frag, scope_params = _scope_filter(scope)
    try:
        effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
        if effective_org:
            org_prefix = (
                "MATCH (_scope:Organization {id: $org}) "
                "MATCH (p:Patient) "
                "OPTIONAL MATCH (p)-[:REGISTERED_AT]->(orgNode:Organization) "
                "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "WHERE (orgNode.id = $org) OR (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
                "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
                "MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
            )
            params: dict = {"org": effective_org}
        else:
            org_prefix = (
                "MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
                f"WHERE true {scope_frag}"
            )
            params = {**scope_params}
        return client.run(
            f"{org_prefix}"
            "OPTIONAL MATCH (a)-[:FOR_EPISODE]->(ep:EpisodeOfCare) "
            "OPTIONAL MATCH (a)-[:TRIGGERED_AT]->(enc:Encounter) "
            "RETURN a.id AS id, a.alert_type AS type, a.rule_name AS rule_name, "
            "       a.severity AS severity, a.status AS status, "
            "       a.guideline AS guideline, a.recommendation_title AS description, "
            "       a.suggested_action AS suggested_action, "
            "       a.match_percent AS match_percent, "
            "       a.actioned AS actioned, a.needs_review AS needs_review, "
            "       toString(a.created_at) AS created_at, "
            "       ep.episode_id AS episode_id, ep.cancer_type AS condition_type, "
            "       enc.id AS encounter_id, toString(enc.date) AS encounter_date, "
            "       p.id AS patient_id "
            "ORDER BY a.created_at DESC LIMIT 200",
            **params,
        )
    finally:
        client.close()


@router.get("/safety-netting/worklist")
def safety_net_worklist(
    scope: CallerScope = Depends(get_caller_scope),
    org_id: Optional[str] = Query(default=None),
):
    """Patient-pathway centric safety-netting worklist for /safety-netting UI."""
    scope = _coerce_scope(scope)
    client = PatientGraphClient()
    scope_frag, scope_params = _scope_filter(scope)
    try:
        effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
        if effective_org:
            org_prefix = (
                "MATCH (_scope:Organization {id: $org}) "
                "MATCH (p:Patient) "
                "WHERE EXISTS { MATCH (p)-[:REGISTERED_AT]->(_scope) } "
                "   OR EXISTS { "
                "     MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "     WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
                "        OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
                "   } "
                "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            )
            params: dict = {"org": effective_org}
        else:
            org_prefix = (
                "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
                + (f"WHERE {ORG_PATIENT_FILTER} " if not scope.is_admin else "")
            )
            params = {**scope_params}

        return client.run(
            f"{org_prefix}"
            "WHERE coalesce(ep.status, '') <> 'merged' "
            "  AND coalesce(ep.status, '') <> 'closed' "
            "  AND coalesce(ep.status, '') <> 'completed' "
            "OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep) "
            "WITH p, ep, "
            "     max(toString(enc.date)) AS last_encounter_date, "
            "     collect(DISTINCT CASE "
            "       WHEN enc IS NULL THEN NULL "
            "       ELSE {"
            "         encounter_id: enc.id, "
            "         date: toString(enc.date), "
            "         milestone_type: r.milestone_type"
            "       } "
            "     END) AS milestones_raw "
            "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert)-[:FOR_EPISODE]->(ep) "
            "WITH p, ep, last_encounter_date, "
            "     [m IN milestones_raw WHERE m IS NOT NULL] AS milestones, "
            "     collect(DISTINCT CASE "
            "       WHEN a IS NULL THEN NULL "
            "       ELSE {"
            "         id: a.id, "
            "         type: a.alert_type, "
            "         rule_name: a.rule_name, "
            "         severity: a.severity, "
            "         status: a.status, "
            "         guideline: a.guideline, "
            "         description: a.recommendation_title, "
            "         suggested_action: a.suggested_action, "
            "         match_percent: a.match_percent, "
            "         actioned: a.actioned, "
            "         needs_review: a.needs_review, "
            "         created_at: toString(a.created_at)"
            "       } "
            "     END) AS alerts_raw "
            "RETURN toString(p.id) AS patient_id, "
            "       p.gender AS gender, "
            "       toString(p.birthDate) AS birth_date, "
            "       ep.episode_id AS episode_id, "
            "       ep.cancer_type AS condition_type, "
            "       ep.status AS status, "
            "       toString(ep.referral_date) AS referral_date, "
            "       ep.referral_route AS referral_route, "
            "       ep.safety_netting_recorded AS safety_netting_recorded, "
            "       ep.needs_review AS needs_review, "
            "       ep.agent_confidence AS confidence, "
            "       ep.agent_reasoning AS agent_reasoning, "
            "       last_encounter_date, "
            "       milestones, "
            "       [a IN alerts_raw WHERE a IS NOT NULL] AS alerts "
            "ORDER BY ep.referral_date ASC",
            **params,
        )
    finally:
        client.close()


@router.patch("/safety-netting/alerts/{alert_id}/action")
def action_css_alert(
    alert_id: str,
    body: ActionAlertRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Mark a safety-net alert as actioned or un-actioned."""
    scope = _coerce_scope(scope)
    client = PatientGraphClient()
    try:
        if not scope.is_admin:
            owner = client.run(
                "MATCH (p:Patient)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert {id: $aid}) "
                "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                "RETURN gp.id AS gp_id",
                aid=alert_id,
            )
            if not owner or owner[0].get("gp_id") not in scope.org_ids:
                raise HTTPException(status_code=404, detail="Alert not found")
        result = client.run(
            "MATCH (a:SafetyNetAlert {id: $aid}) "
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
