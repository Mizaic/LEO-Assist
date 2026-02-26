"""Cohort management endpoints.

Create, list, and resolve patient cohorts by various filters.
Cohort definitions are stored as Cohort nodes in the Patient Graph.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ────────────────────────────────────────────


class CohortFilter(BaseModel):
    org_id: Optional[str] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    condition_codes: Optional[List[str]] = None
    episode_status: Optional[List[str]] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    custom_cypher: Optional[str] = None


class CohortCreateRequest(BaseModel):
    name: str
    description: str = ""
    filters: CohortFilter


class CohortResponse(BaseModel):
    cohort_id: str
    name: str
    description: str
    filters: Dict[str, Any]
    patient_count: int = 0
    created_at: Optional[str] = None


class CohortPatientsResponse(BaseModel):
    cohort_id: str
    patient_ids: List[str]
    total: int


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/cohorts", response_model=CohortResponse)
def create_cohort(body: CohortCreateRequest):
    """Create a new saved cohort definition."""
    client = PatientGraphClient()
    cohort_id = f"COH_{uuid4().hex[:12]}"
    filters_json = body.filters.model_dump_json()

    try:
        patient_count = _resolve_patient_count(client, body.filters)

        client.run(
            "CREATE (c:Cohort { "
            "    cohort_id: $cid, name: $name, description: $desc, "
            "    filters: $filters, patient_count: $count, "
            "    created_at: datetime(), created_by: 'analytics_api' "
            "})",
            cid=cohort_id, name=body.name, desc=body.description,
            filters=filters_json, count=patient_count,
        )

        return CohortResponse(
            cohort_id=cohort_id,
            name=body.name,
            description=body.description,
            filters=body.filters.model_dump(),
            patient_count=patient_count,
        )
    finally:
        client.close()


@router.get("/cohorts", response_model=List[CohortResponse])
def list_cohorts():
    """List all saved cohort definitions."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (c:Cohort) "
            "RETURN c.cohort_id AS cohort_id, c.name AS name, "
            "       c.description AS description, c.filters AS filters, "
            "       c.patient_count AS patient_count, "
            "       toString(c.created_at) AS created_at "
            "ORDER BY c.created_at DESC"
        )
        result = []
        for row in rows:
            filters_raw = row.get("filters", "{}")
            try:
                filters = json.loads(filters_raw) if isinstance(filters_raw, str) else filters_raw
            except (json.JSONDecodeError, TypeError):
                filters = {}
            result.append(CohortResponse(
                cohort_id=row["cohort_id"],
                name=row.get("name", ""),
                description=row.get("description", ""),
                filters=filters,
                patient_count=row.get("patient_count", 0),
                created_at=row.get("created_at"),
            ))
        return result
    finally:
        client.close()


@router.get("/cohorts/{cohort_id}/patients", response_model=CohortPatientsResponse)
def resolve_cohort(cohort_id: str):
    """Resolve a cohort to a list of patient IDs."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) RETURN c.filters AS filters",
            cid=cohort_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cohort not found")

        filters_raw = rows[0].get("filters", "{}")
        try:
            filters_dict = json.loads(filters_raw) if isinstance(filters_raw, str) else filters_raw
        except (json.JSONDecodeError, TypeError):
            filters_dict = {}

        filters = CohortFilter(**filters_dict)
        patient_ids = _resolve_patients(client, filters)

        client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) SET c.patient_count = $count",
            cid=cohort_id, count=len(patient_ids),
        )

        return CohortPatientsResponse(
            cohort_id=cohort_id,
            patient_ids=patient_ids,
            total=len(patient_ids),
        )
    finally:
        client.close()


@router.delete("/cohorts/{cohort_id}")
def delete_cohort(cohort_id: str):
    """Delete a saved cohort definition."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) DELETE c RETURN count(c) AS deleted",
            cid=cohort_id,
        )
        if not rows or rows[0].get("deleted", 0) == 0:
            raise HTTPException(status_code=404, detail="Cohort not found")
        return {"success": True}
    finally:
        client.close()


# ── Filter resolution helpers ────────────────────────────────────────────


def _build_where_clauses(f: CohortFilter) -> tuple[str, Dict[str, Any]]:
    """Build Cypher WHERE clauses from cohort filters."""
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if f.org_id:
        clauses.append("EXISTS { MATCH (p)-[:REGISTERED_AT]->(o:Organization {id: $org_id}) }")
        params["org_id"] = f.org_id

    if f.date_range_start:
        clauses.append("EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) WHERE toString(e.date) >= $date_start }")
        params["date_start"] = f.date_range_start

    if f.date_range_end:
        clauses.append("EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) WHERE toString(e.date) <= $date_end }")
        params["date_end"] = f.date_range_end

    if f.condition_codes:
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->()-[:DOCUMENTS]->(c) "
            "WHERE toString(c.conceptId) IN $codes }"
        )
        params["codes"] = f.condition_codes

    if f.episode_status:
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_EPISODE]->(ep:CancerEpisode) "
            "WHERE ep.status IN $ep_statuses }"
        )
        params["ep_statuses"] = f.episode_status

    if f.age_min is not None:
        clauses.append("p.age >= $age_min")
        params["age_min"] = f.age_min

    if f.age_max is not None:
        clauses.append("p.age <= $age_max")
        params["age_max"] = f.age_max

    return " AND ".join(clauses) if clauses else "true", params


def _resolve_patients(client: PatientGraphClient, f: CohortFilter) -> List[str]:
    """Resolve a filter to a list of patient IDs."""
    if f.custom_cypher:
        rows = client.run(f.custom_cypher)
        return [str(r.get("patient_id", r.get("id", ""))) for r in rows if r]

    where_clause, params = _build_where_clauses(f)
    rows = client.run(
        f"MATCH (p:Patient) WHERE {where_clause} "
        f"RETURN toString(p.id) AS patient_id ORDER BY p.id LIMIT 10000",
        **params,
    )
    return [str(r["patient_id"]) for r in rows]


def _resolve_patient_count(client: PatientGraphClient, f: CohortFilter) -> int:
    """Count patients matching a filter without returning all IDs."""
    if f.custom_cypher:
        rows = client.run(f"WITH {{ {f.custom_cypher} }} AS sub RETURN count(*) AS cnt")
        return rows[0].get("cnt", 0) if rows else 0

    where_clause, params = _build_where_clauses(f)
    rows = client.run(
        f"MATCH (p:Patient) WHERE {where_clause} RETURN count(p) AS cnt",
        **params,
    )
    return rows[0].get("cnt", 0) if rows else 0
