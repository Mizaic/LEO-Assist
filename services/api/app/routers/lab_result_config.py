"""Knowledge Graph-backed lab result metadata API.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import CodingGraphClient
from app.deps import get_caller_scope_from_request, require_admin
from libs.auth.org_scope import CallerScope
from libs.cypher.lab_result_config_queries import (
    DELETE_INTERPRETATION,
    DELETE_REFERENCE_RANGE,
    DELETE_UNIT_CONVERSION,
    GET_LAB_RESULT_CONFIG,
    LIST_LAB_RESULT_CONFIGS,
    UPSERT_INTERPRETATION,
    UPSERT_LAB_RESULT_CONFIG,
    UPSERT_REFERENCE_RANGE,
    UPSERT_UNIT_CONVERSION,
)

router = APIRouter(prefix="/api/lab-result-configs", tags=["lab-result-configs"])


class LabConfigUpsert(BaseModel):
    display_name: str = Field(..., min_length=1)
    canonical_unit: str = Field(..., min_length=1)
    source: str = "manual"


class UnitConversionUpsert(BaseModel):
    unit: str = Field(..., min_length=1)
    factor: float = 1.0
    offset: float = 0.0


class ReferenceRangeUpsert(BaseModel):
    range_id: str | None = None
    sex: str | None = "all"
    age_min: float | None = None
    age_max: float | None = None
    low: float | None = None
    high: float | None = None
    critical_low: float | None = None
    critical_high: float | None = None
    source: str = "manual"
    org_id: str = ""


class InterpretationUpsert(BaseModel):
    classification: str = Field(..., min_length=1)
    finding_concept_id: str = Field(..., min_length=1)


def _clean_config(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "concept_id": row.get("concept_id"),
        "display_name": row.get("display_name"),
        "canonical_unit": row.get("canonical_unit"),
        "source": row.get("source"),
        "updated_at": row.get("updated_at"),
        "conversions": _clean_items(row.get("conversions") or [], "unit"),
        "ranges": _clean_items(row.get("ranges") or [], "range_id"),
        "interpretations": _clean_items(
            row.get("interpretations") or [], "classification"
        ),
    }


def _range_read_params(scope: CallerScope) -> dict[str, Any]:
    if scope.is_admin:
        return {"include_all": True, "org_id": ""}
    return {"include_all": False, "org_id": scope.primary_org_id or ""}


def _clean_items(
    items: list[dict[str, Any]], required_key: str
) -> list[dict[str, Any]]:
    out = []
    for item in items:
        if not item or item.get(required_key) in (None, ""):
            continue
        out.append(dict(item))
    return out


@router.get("")
def list_lab_result_configs(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = session.run(LIST_LAB_RESULT_CONFIGS, q=q, limit=limit).data()
        return {"items": rows}
    finally:
        client.close()


@router.get("/{concept_id}")
def get_lab_result_config(
    concept_id: str,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                GET_LAB_RESULT_CONFIG,
                concept_id=concept_id,
                **_range_read_params(scope),
            ).single()
        item = _clean_config(dict(row) if row else None)
        if item is None:
            raise HTTPException(status_code=404, detail="Lab result config not found")
        return {"item": item}
    finally:
        client.close()


@router.put("/{concept_id}")
def upsert_lab_result_config(
    concept_id: str,
    body: LabConfigUpsert,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_LAB_RESULT_CONFIG,
                concept_id=concept_id,
                display_name=body.display_name,
                canonical_unit=body.canonical_unit,
                source=body.source,
                updated_by=scope.email or "unknown",
            )
        return {"concept_id": concept_id, "status": "updated"}
    finally:
        client.close()


@router.post("/{concept_id}/conversions")
def upsert_unit_conversion(
    concept_id: str,
    body: UnitConversionUpsert,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                UPSERT_UNIT_CONVERSION,
                concept_id=concept_id,
                unit=body.unit,
                factor=body.factor,
                offset=body.offset,
                updated_by=scope.email or "unknown",
            ).single()
        return {"conversion_id": result.get("conversion_id"), "status": "updated"}
    finally:
        client.close()


@router.post("/{concept_id}/ranges")
def upsert_reference_range(
    concept_id: str,
    body: ReferenceRangeUpsert,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    range_id = body.range_id or str(uuid.uuid4())
    client = CodingGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_REFERENCE_RANGE,
                range_id=range_id,
                concept_id=concept_id,
                sex=body.sex,
                age_min=body.age_min,
                age_max=body.age_max,
                low=body.low,
                high=body.high,
                critical_low=body.critical_low,
                critical_high=body.critical_high,
                source=body.source,
                org_id=str(body.org_id or "").strip(),
                updated_by=scope.email or "unknown",
            )
        return {"range_id": range_id, "status": "updated"}
    finally:
        client.close()


@router.post("/{concept_id}/interpretations")
def upsert_interpretation(
    concept_id: str,
    body: InterpretationUpsert,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            result = session.run(
                UPSERT_INTERPRETATION,
                concept_id=concept_id,
                classification=body.classification.strip().lower(),
                finding_concept_id=body.finding_concept_id,
                updated_by=scope.email or "unknown",
            ).single()
        if not result:
            raise HTTPException(status_code=404, detail="Finding concept not found")
        return {"classification": body.classification, "status": "updated"}
    finally:
        client.close()


@router.delete("/{concept_id}/ranges/{range_id}")
def delete_reference_range(
    concept_id: str,
    range_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    return _delete_child(DELETE_REFERENCE_RANGE, concept_id, scope, range_id=range_id)


@router.delete("/{concept_id}/conversions/{unit}")
def delete_unit_conversion(
    concept_id: str,
    unit: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    return _delete_child(DELETE_UNIT_CONVERSION, concept_id, scope, unit=unit)


@router.delete("/{concept_id}/interpretations/{classification}")
def delete_interpretation(
    concept_id: str,
    classification: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    return _delete_child(
        DELETE_INTERPRETATION,
        concept_id,
        scope,
        classification=classification,
    )


def _delete_child(
    query: str,
    concept_id: str,
    scope: CallerScope,
    **params: Any,
) -> dict[str, Any]:
    client = CodingGraphClient()
    try:
        with client.session() as session:
            result = session.run(query, concept_id=concept_id, **params).single()
        deleted = int(result.get("deleted") if result else 0)
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Lab config child not found")
        return {"concept_id": concept_id, "status": "deleted"}
    finally:
        client.close()
