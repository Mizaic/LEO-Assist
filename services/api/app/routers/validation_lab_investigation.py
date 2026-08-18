"""Validation Lab NCR investigation store and redacted Atlas journal.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Atlas: DI-ED5A9AC3
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_admin_or_service
from libs.atlas_qms.investigation_store import load_investigation, log_event, save_cases
from libs.atlas_qms.ncr_client import (
    NcrClientError,
    NcrNotConfigured,
    list_product_ncr_activity,
)
from libs.auth.org_scope import CallerScope

router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])


class CaseBody(BaseModel):
    run_id: str = ""
    patient_id: str = ""
    patient_name: str = ""
    nhs_number: str = ""
    ubrn: str = ""
    status: str = ""


class SaveCasesBody(BaseModel):
    cases: list[CaseBody] = Field(default_factory=list)
    title: str = Field(default="", max_length=200)


class EventBody(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=2000)


@router.get("/ncrs/{nc_id}/investigation")
def get_investigation(
    nc_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    if not nc_id.strip():
        raise HTTPException(status_code=400, detail="A ticket id is required.")
    return load_investigation(nc_id)


@router.put("/ncrs/{nc_id}/investigation/cases")
def put_investigation_cases(
    nc_id: str,
    body: SaveCasesBody,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    if not nc_id.strip():
        raise HTTPException(status_code=400, detail="A ticket id is required.")
    return save_cases(nc_id, [row.model_dump() for row in body.cases], title=body.title)


@router.post("/ncrs/{nc_id}/investigation/events")
def post_investigation_event(
    nc_id: str,
    body: EventBody,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    if not nc_id.strip():
        raise HTTPException(status_code=400, detail="A ticket id is required.")
    return log_event(nc_id, body.kind, body.text)


@router.get("/ncrs/{nc_id}/activity")
def get_ncr_activity(
    nc_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    try:
        items = list_product_ncr_activity(nc_id)
    except NcrNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NcrClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"items": items}
