"""Domain-agnostic patient list and detail endpoints (EPR view).

Atlas trace:
  DO: DO-EBF0B124, DO-5D3EA371
  DI: DI-0ADA35BF, DI-357A7468
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EBF0B124")

All patients in the caller's org scope are returned regardless of episode
type. Results are paginated and filterable by patient ID search, condition
type, and active alert presence.

Endpoints:
  GET /analytics/patients         -- paginated, filterable patient list
  GET /analytics/patients/facets  -- distinct condition types for filter UI
  GET /analytics/patients/{id}    -- patient detail with all episodes
  GET /analytics/patients/{id}/timeline -- activity timeline items

Cypher queries live in patients_epr_queries.py to keep this file concise.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

from .patients_epr_queries import (
    COUNT_PATIENTS_ADMIN,
    COUNT_PATIENTS_SCOPED,
    FACETS_ADMIN,
    FACETS_SCOPED,
    GET_PATIENT_DETAIL_ADMIN,
    GET_PATIENT_DETAIL_SCOPED,
    GET_TIMELINE_ADMIN,
    GET_TIMELINE_SCOPED,
    LIST_PATIENTS_ADMIN,
    LIST_PATIENTS_SCOPED,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PatientSummary(BaseModel):
    patient_id: str
    display_name: Optional[str] = None
    nhs_number: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    practice_name: Optional[str] = None
    episode_count: int = 0
    encounter_count: int = 0
    last_activity: Optional[str] = None
    active_alert_count: int = 0
    document_count: int = 0
    referral_count: int = 0
    coded_concept_count: int = 0
    semantic_tags: list[str] = []
    condition_types: list[str] = []


class EpisodeSummary(BaseModel):
    episode_id: Optional[str] = None
    condition_type: Optional[str] = None
    status: Optional[str] = None
    referral_date: Optional[str] = None
    end_date: Optional[str] = None
    first_presentation_date: Optional[str] = None
    inferred_outcome: Optional[str] = None
    staging_value: Optional[str] = None
    staging_early_late: Optional[str] = None
    referral_route: Optional[str] = None
    place_of_presentation: Optional[str] = None
    prior_consultations_n: Optional[int] = None
    safety_netting_recorded: Optional[bool] = None


class PatientDetail(BaseModel):
    patient_id: str
    display_name: Optional[str] = None
    nhs_number: Optional[str] = None
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


class PatientFacetsResponse(BaseModel):
    condition_types: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_patient_summary(row: dict[str, Any]) -> PatientSummary:
    raw_tags = [t for t in (row.get("raw_tags") or []) if t]
    return PatientSummary(
        patient_id=row.get("patient_id", ""),
        display_name=row.get("display_name") or row.get("patient_id", ""),
        nhs_number=row.get("nhs_number"),
        gender=row.get("gender"),
        birth_date=row.get("birth_date"),
        practice_name=row.get("practice_name"),
        episode_count=int(row.get("episode_count") or 0),
        encounter_count=int(row.get("encounter_count") or 0),
        last_activity=row.get("last_activity"),
        active_alert_count=int(row.get("active_alert_count") or 0),
        document_count=int(row.get("document_count") or 0),
        referral_count=int(row.get("referral_count") or 0),
        coded_concept_count=int(row.get("coded_concept_count") or 0),
        semantic_tags=raw_tags,
        condition_types=[ct for ct in (row.get("condition_types") or []) if ct],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/patients", response_model=PatientsListResponse)
def list_patients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=100),
    condition_type: Optional[str] = Query(default=None, max_length=100),
    has_alerts: Optional[bool] = Query(default=None),
    scope: CallerScope = Depends(get_caller_scope),
) -> PatientsListResponse:
    """List all patients in the caller's org scope.

    Supports filtering by patient ID search, condition type, and active
    alert presence. Admin users see all patients; scoped users see only
    their org hierarchy.
    """
    skip = (page - 1) * page_size
    base_params: dict[str, Any] = {
        "search": search or None,
        "condition_type": condition_type or None,
        "has_alerts": has_alerts,
        "skip": skip,
        "limit": page_size,
    }

    if scope.is_admin:
        count_query, list_query = COUNT_PATIENTS_ADMIN, LIST_PATIENTS_ADMIN
        cypher_params = base_params
    else:
        count_query, list_query = COUNT_PATIENTS_SCOPED, LIST_PATIENTS_SCOPED
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
        total=total, page=page, page_size=page_size, patients=patients
    )


@router.get("/patients/facets", response_model=PatientFacetsResponse)
def get_patient_facets(
    scope: CallerScope = Depends(get_caller_scope),
) -> PatientFacetsResponse:
    """Return distinct condition types present in the caller's patient cohort.

    Used to populate the condition-type filter tabs in the patient list UI.
    Admin users see all condition types; scoped users see only those within
    their org hierarchy.
    """
    if scope.is_admin:
        query = FACETS_ADMIN
        cypher_params: dict[str, Any] = {}
    else:
        query = FACETS_SCOPED
        cypher_params = {"scope_org_ids": scope.org_ids}

    client = PatientGraphClient()
    try:
        rows = client.run(query, **cypher_params)
    except Exception as exc:
        logger.error("patients_epr.facets_failed err=%s", exc)
        raise
    finally:
        client.close()

    return PatientFacetsResponse(
        condition_types=[r["condition_type"] for r in rows if r.get("condition_type")]
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
        query = GET_PATIENT_DETAIL_ADMIN
        cypher_params: dict[str, Any] = {"patient_id": patient_id}
    else:
        query = GET_PATIENT_DETAIL_SCOPED
        cypher_params = {"scope_org_ids": scope.org_ids, "patient_id": patient_id}

    client = PatientGraphClient()
    try:
        rows = client.run(query, **cypher_params)
    finally:
        client.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found.")

    row = rows[0]
    episodes = [
        EpisodeSummary(
            episode_id=ep.get("episode_id"),
            condition_type=ep.get("condition_type"),
            status=ep.get("status"),
            referral_date=ep.get("referral_date"),
            end_date=ep.get("end_date"),
            first_presentation_date=ep.get("first_presentation_date"),
            inferred_outcome=ep.get("inferred_outcome"),
            staging_value=ep.get("staging_value"),
            staging_early_late=ep.get("staging_early_late"),
            referral_route=ep.get("referral_route"),
            place_of_presentation=ep.get("place_of_presentation"),
            prior_consultations_n=(
                int(ep["prior_consultations_n"])
                if ep.get("prior_consultations_n") is not None
                else None
            ),
            safety_netting_recorded=ep.get("safety_netting_recorded"),
        )
        for ep in (row.get("episodes") or [])
        if ep and ep.get("episode_id")
    ]

    return PatientDetail(
        patient_id=row.get("patient_id", patient_id),
        display_name=row.get("display_name") or row.get("patient_id", patient_id),
        nhs_number=row.get("nhs_number"),
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
        query = GET_TIMELINE_ADMIN
        cypher_params: dict[str, Any] = {"patient_id": patient_id}
    else:
        query = GET_TIMELINE_SCOPED
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
