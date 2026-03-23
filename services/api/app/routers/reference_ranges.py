"""Reference range CRUD endpoints with tenant scoping."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.reference_range_queries import (
    DELETE_REFERENCE_RANGE,
    GET_REFERENCE_RANGE_BY_ID,
    LIST_REFERENCE_RANGES,
    UPSERT_REFERENCE_RANGE,
)

router = APIRouter(prefix="/api/reference-ranges", tags=["reference-ranges"])


class ReferenceRangeUpsert(BaseModel):
    concept_id: str = Field(..., min_length=1)
    preferred_term: str = Field(..., min_length=1)
    unit: str | None = None
    sex: str | None = Field(default="all")
    age_min: int | None = None
    age_max: int | None = None
    low: float | None = None
    high: float | None = None
    critical_low: float | None = None
    critical_high: float | None = None
    source: str = "manual"
    org_id: str | None = None


def _effective_org_id(scope: CallerScope, requested_org_id: str | None) -> str | None:
    if scope.is_admin:
        return requested_org_id
    if not scope.primary_org_id:
        raise HTTPException(status_code=403, detail="No primary org in caller scope")
    if requested_org_id and requested_org_id != scope.primary_org_id:
        raise HTTPException(status_code=403, detail="Cannot modify another organization's ranges")
    return scope.primary_org_id


@router.get("")
def list_reference_ranges(
    concept_id: str | None = Query(None),
    org_id: str | None = Query(None),
    include_platform: bool = Query(True),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    effective_org_id = None if scope.is_admin else scope.primary_org_id
    if scope.is_admin:
        effective_org_id = org_id

    client = PatientGraphClient()
    try:
        with client.session() as s:
            rows = s.run(
                LIST_REFERENCE_RANGES,
                org_id=effective_org_id,
                include_platform=include_platform,
                concept_id=concept_id,
            ).data()
        return {"items": rows}
    finally:
        client.close()


@router.post("", status_code=201)
def create_reference_range(
    body: ReferenceRangeUpsert,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        range_id = str(uuid.uuid4())
        effective_org_id = _effective_org_id(scope, body.org_id)
        with client.session() as s:
            s.run(
                UPSERT_REFERENCE_RANGE,
                range_id=range_id,
                concept_id=body.concept_id,
                preferred_term=body.preferred_term,
                unit=body.unit,
                sex=body.sex,
                age_min=body.age_min,
                age_max=body.age_max,
                low=body.low,
                high=body.high,
                critical_low=body.critical_low,
                critical_high=body.critical_high,
                source=body.source,
                org_id=effective_org_id,
                updated_by=scope.email or "unknown",
            )
        return {"range_id": range_id, "status": "created"}
    finally:
        client.close()


@router.put("/{range_id}")
def update_reference_range(
    range_id: str,
    body: ReferenceRangeUpsert,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            existing = s.run(GET_REFERENCE_RANGE_BY_ID, range_id=range_id).single()
            if not existing:
                raise HTTPException(status_code=404, detail="Reference range not found")
            current_org_id = existing.get("org_id")
            if not scope.is_admin and current_org_id != scope.primary_org_id:
                raise HTTPException(status_code=403, detail="Cannot modify another organization's range")
            effective_org_id = _effective_org_id(scope, body.org_id if body.org_id is not None else current_org_id)
            s.run(
                UPSERT_REFERENCE_RANGE,
                range_id=range_id,
                concept_id=body.concept_id,
                preferred_term=body.preferred_term,
                unit=body.unit,
                sex=body.sex,
                age_min=body.age_min,
                age_max=body.age_max,
                low=body.low,
                high=body.high,
                critical_low=body.critical_low,
                critical_high=body.critical_high,
                source=body.source,
                org_id=effective_org_id,
                updated_by=scope.email or "unknown",
            )
        return {"range_id": range_id, "status": "updated"}
    finally:
        client.close()


@router.delete("/{range_id}")
def delete_reference_range(
    range_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            existing = s.run(GET_REFERENCE_RANGE_BY_ID, range_id=range_id).single()
            if not existing:
                raise HTTPException(status_code=404, detail="Reference range not found")
            if not scope.is_admin and existing.get("org_id") != scope.primary_org_id:
                raise HTTPException(status_code=403, detail="Cannot delete another organization's range")
            result = s.run(DELETE_REFERENCE_RANGE, range_id=range_id).single()
            if not result or int(result.get("deleted") or 0) == 0:
                raise HTTPException(status_code=404, detail="Reference range not found")
        return {"range_id": range_id, "status": "deleted"}
    finally:
        client.close()
