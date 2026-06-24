"""Domain-agnostic patient list and detail endpoints (EPR view).

Atlas trace:
  DO: DO-EBF0B124, DO-5D3EA371
  DI: DI-0ADA35BF, DI-357A7468
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EBF0B124")

All patients in the caller's org scope are returned regardless of episode
type. There is no cancer-type filter. Results are paginated and searchable
by patient ID.

Endpoints:
  GET /analytics/patients          -- paginated patient list
  GET /analytics/patients/{id}     -- patient detail with all episodes
  GET /analytics/patients/{id}/timeline -- activity timeline items
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, ORG_PATIENT_FILTER, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_ORG_GUARD = ORG_PATIENT_FILTER

_LIST_PATIENTS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE " + _ORG_GUARD + " "
    "AND ($search IS NULL OR p.id CONTAINS $search) "
    "WITH p "
    "ORDER BY p.id ASC "
    "SKIP $skip LIMIT $limit "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "WITH p, gp, "
    "count(DISTINCT ep) AS episode_count, "
    "count(DISTINCT enc) AS encounter_count, "
    "max(toString(enc.date)) AS last_activity, "
    "count(DISTINCT alert) AS active_alert_count, "
    "collect(DISTINCT coalesce(ep.condition_type, ep.cancer_type)) AS condition_types "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  episode_count, "
    "  encounter_count, "
    "  last_activity, "
    "  active_alert_count, "
    "  [ct IN condition_types WHERE ct IS NOT NULL AND ct <> ''] AS condition_types"
)

_LIST_PATIENTS_ADMIN = (
    "MATCH (p:Patient) "
    "WHERE ($search IS NULL OR p.id CONTAINS $search) "
    "WITH p "
    "ORDER BY p.id ASC "
    "SKIP $skip LIMIT $limit "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  WHERE NOT ep.status IN ['merged', 'closed_phantom', 'closed_related'] "
    "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "WITH p, gp, "
    "count(DISTINCT ep) AS episode_count, "
    "count(DISTINCT enc) AS encounter_count, "
    "max(toString(enc.date)) AS last_activity, "
    "count(DISTINCT alert) AS active_alert_count, "
    "collect(DISTINCT coalesce(ep.condition_type, ep.cancer_type)) AS condition_types "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  episode_count, "
    "  encounter_count, "
    "  last_activity, "
    "  active_alert_count, "
    "  [ct IN condition_types WHERE ct IS NOT NULL AND ct <> ''] AS condition_types"
)

_COUNT_PATIENTS_SCOPED = (
    "MATCH (p:Patient) "
    "WHERE " + _ORG_GUARD + " "
    "AND ($search IS NULL OR p.id CONTAINS $search) "
    "RETURN count(p) AS total"
)

_COUNT_PATIENTS_ADMIN = (
    "MATCH (p:Patient) "
    "WHERE ($search IS NULL OR p.id CONTAINS $search) "
    "RETURN count(p) AS total"
)

_GET_PATIENT_DETAIL_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  count(DISTINCT alert) AS active_alert_count, "
    "  collect(DISTINCT { "
    "    episode_id: ep.episode_id, "
    "    condition_type: coalesce(ep.condition_type, ep.cancer_type), "
    "    status: ep.status, "
    "    referral_date: toString(ep.referral_date), "
    "    end_date: toString(ep.end_date), "
    "    inferred_outcome: ep.inferred_outcome "
    "  }) AS episodes"
)

_GET_PATIENT_DETAIL_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) "
    "OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:Organization) "
    "OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(alert:SafetyNetAlert) "
    "  WHERE alert.resolved_at IS NULL "
    "RETURN "
    "  p.id AS patient_id, "
    "  p.gender AS gender, "
    "  p.birthDate AS birth_date, "
    "  gp.name AS practice_name, "
    "  count(DISTINCT alert) AS active_alert_count, "
    "  collect(DISTINCT { "
    "    episode_id: ep.episode_id, "
    "    condition_type: coalesce(ep.condition_type, ep.cancer_type), "
    "    status: ep.status, "
    "    referral_date: toString(ep.referral_date), "
    "    end_date: toString(ep.end_date), "
    "    inferred_outcome: ep.inferred_outcome "
    "  }) AS episodes"
)

_GET_TIMELINE_SCOPED = (
    "MATCH (p:Patient {id: $patient_id}) "
    "WHERE " + _ORG_GUARD + " "
    "CALL { "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "  RETURN 'encounter' AS item_type, enc.id AS item_id, "
    "         toString(enc.date) AS item_date, "
    "         coalesce(enc.consultation_type, 'Encounter') AS label, "
    "         null AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  RETURN 'episode' AS item_type, ep.episode_id AS item_id, "
    "         toString(ep.referral_date) AS item_date, "
    "         coalesce(ep.condition_type, ep.cancer_type, 'Episode') AS label, "
    "         ep.status AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
    "  RETURN 'alert' AS item_type, a.id AS item_id, "
    "         toString(a.created_at) AS item_date, "
    "         coalesce(a.alert_type, 'Alert') AS label, "
    "         a.resolved_at AS extra "
    "} "
    "WITH item_type, item_id, item_date, label, extra "
    "WHERE item_id IS NOT NULL AND item_date IS NOT NULL "
    "RETURN item_type, item_id, item_date, label, extra "
    "ORDER BY item_date DESC "
    "LIMIT 100"
)

_GET_TIMELINE_ADMIN = (
    "MATCH (p:Patient {id: $patient_id}) "
    "CALL { "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
    "  RETURN 'encounter' AS item_type, enc.id AS item_id, "
    "         toString(enc.date) AS item_date, "
    "         coalesce(enc.consultation_type, 'Encounter') AS label, "
    "         null AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
    "  RETURN 'episode' AS item_type, ep.episode_id AS item_id, "
    "         toString(ep.referral_date) AS item_date, "
    "         coalesce(ep.condition_type, ep.cancer_type, 'Episode') AS label, "
    "         ep.status AS extra "
    "  UNION "
    "  WITH p "
    "  OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert) "
    "  RETURN 'alert' AS item_type, a.id AS item_id, "
    "         toString(a.created_at) AS item_date, "
    "         coalesce(a.alert_type, 'Alert') AS label, "
    "         a.resolved_at AS extra "
    "} "
    "WITH item_type, item_id, item_date, label, extra "
    "WHERE item_id IS NOT NULL AND item_date IS NOT NULL "
    "RETURN item_type, item_id, item_date, label, extra "
    "ORDER BY item_date DESC "
    "LIMIT 100"
)

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PatientSummary(BaseModel):
    patient_id: str
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    practice_name: Optional[str] = None
    episode_count: int = 0
    encounter_count: int = 0
    last_activity: Optional[str] = None
    active_alert_count: int = 0
    condition_types: list[str] = []


class EpisodeSummary(BaseModel):
    episode_id: Optional[str] = None
    condition_type: Optional[str] = None
    status: Optional[str] = None
    referral_date: Optional[str] = None
    end_date: Optional[str] = None
    inferred_outcome: Optional[str] = None


class PatientDetail(BaseModel):
    patient_id: str
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    practice_name: Optional[str] = None
    active_alert_count: int = 0
    episodes: list[EpisodeSummary] = []


class TimelineItem(BaseModel):
    item_type: str
    item_id: str
    item_date: str
    label: str
    extra: Optional[str] = None


class PatientsListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    patients: list[PatientSummary]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_patient_summary(row: dict[str, Any]) -> PatientSummary:
    return PatientSummary(
        patient_id=row.get("patient_id", ""),
        gender=row.get("gender"),
        birth_date=row.get("birth_date"),
        practice_name=row.get("practice_name"),
        episode_count=int(row.get("episode_count") or 0),
        encounter_count=int(row.get("encounter_count") or 0),
        last_activity=row.get("last_activity"),
        active_alert_count=int(row.get("active_alert_count") or 0),
        condition_types=[
            ct for ct in (row.get("condition_types") or []) if ct
        ],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/patients", response_model=PatientsListResponse)
def list_patients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=100),
    scope: CallerScope = Depends(get_caller_scope),
) -> PatientsListResponse:
    """List all patients in the caller's org scope.

    No cancer-type filter is applied. All episode types are included.
    Admin users see all patients; scoped users see only their org hierarchy.
    """
    skip = (page - 1) * page_size
    base_params: dict[str, Any] = {
        "search": search or None,
        "skip": skip,
        "limit": page_size,
    }

    if scope.is_admin:
        count_query = _COUNT_PATIENTS_ADMIN
        list_query = _LIST_PATIENTS_ADMIN
        cypher_params = base_params
    else:
        count_query = _COUNT_PATIENTS_SCOPED
        list_query = _LIST_PATIENTS_SCOPED
        cypher_params = {**base_params, "scope_org_ids": scope.org_ids}

    client = PatientGraphClient()
    try:
        count_rows = client.run(count_query, **cypher_params)
        total = int((count_rows[0].get("total") or 0) if count_rows else 0)
        data_rows = client.run(list_query, **cypher_params)
    except Exception as exc:
        logger.error("patients_epr.list_failed err=%s", exc)
        raise
    finally:
        client.close()

    patients = [_row_to_patient_summary(r) for r in data_rows]
    return PatientsListResponse(
        total=total,
        page=page,
        page_size=page_size,
        patients=patients,
    )


@router.get("/patients/{patient_id}", response_model=PatientDetail)
def get_patient_detail(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> PatientDetail:
    """Return full patient detail including all episodes.

    No episode-type filter is applied.
    Admin users can access any patient; scoped users restricted to their org.
    """
    if scope.is_admin:
        query = _GET_PATIENT_DETAIL_ADMIN
        cypher_params: dict[str, Any] = {"patient_id": patient_id}
    else:
        query = _GET_PATIENT_DETAIL_SCOPED
        cypher_params = {"scope_org_ids": scope.org_ids, "patient_id": patient_id}

    client = PatientGraphClient()
    try:
        rows = client.run(query, **cypher_params)
    finally:
        client.close()

    if not rows:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Patient not found.")

    row = rows[0]
    raw_episodes = row.get("episodes") or []
    episodes = [
        EpisodeSummary(
            episode_id=ep.get("episode_id"),
            condition_type=ep.get("condition_type"),
            status=ep.get("status"),
            referral_date=ep.get("referral_date"),
            end_date=ep.get("end_date"),
            inferred_outcome=ep.get("inferred_outcome"),
        )
        for ep in raw_episodes
        if ep and ep.get("episode_id")
    ]

    return PatientDetail(
        patient_id=row.get("patient_id", patient_id),
        gender=row.get("gender"),
        birth_date=row.get("birth_date"),
        practice_name=row.get("practice_name"),
        active_alert_count=int(row.get("active_alert_count") or 0),
        episodes=episodes,
    )


@router.get("/patients/{patient_id}/timeline", response_model=list[TimelineItem])
def get_patient_timeline(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[TimelineItem]:
    """Return all activity timeline items for a patient in date order.

    Includes encounters, episode starts, and safety netting alerts.
    Admin users can access any patient; scoped users restricted to their org.
    """
    if scope.is_admin:
        query = _GET_TIMELINE_ADMIN
        cypher_params: dict[str, Any] = {"patient_id": patient_id}
    else:
        query = _GET_TIMELINE_SCOPED
        cypher_params = {"scope_org_ids": scope.org_ids, "patient_id": patient_id}

    client = PatientGraphClient()
    try:
        rows = client.run(query, **cypher_params)
    finally:
        client.close()

    return [
        TimelineItem(
            item_type=r.get("item_type", ""),
            item_id=r.get("item_id", ""),
            item_date=r.get("item_date", ""),
            label=r.get("label", ""),
            extra=str(r.get("extra")) if r.get("extra") else None,
        )
        for r in rows
    ]
