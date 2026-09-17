"""Admin spend true-up and soft encounter quota routes.

Atlas trace:
  DI: DI-3E297B23
  DI: DI-6D87C32F
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.llm_spend_true_up.entitlement import list_quotas, upsert_quota
from libs.llm_spend_true_up.queries import GET_LATEST_TRUE_UP

router = APIRouter(prefix="/pricing", tags=["pricing"])


class EncounterQuotaBody(BaseModel):
    monthlyLimit: int = Field(ge=0)
    orgName: str = ""


def _require_admin(scope: CallerScope) -> None:
    if not scope.is_admin:
        raise HTTPException(403, "Admin permission required")


def _environment() -> str:
    return os.getenv("LEO_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "prod"


@router.get("/true-up")
def get_true_up(scope: CallerScope = Depends(get_caller_scope)) -> dict[str, Any]:
    _require_admin(scope)
    pg = PatientGraphClient()
    try:
        rows = pg.run(GET_LATEST_TRUE_UP, environment=_environment())
        if not rows:
            return {"check": None, "note": _account_note()}
        return {"check": rows[0], "note": _account_note()}
    finally:
        pg.close()


@router.get("/encounter-quotas")
def get_encounter_quotas(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    pg = PatientGraphClient()
    try:
        return {"quotas": list_quotas(pg)}
    finally:
        pg.close()


@router.put("/orgs/{org_id}/encounter-quota")
def put_encounter_quota(
    org_id: str,
    body: EncounterQuotaBody,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    pg = PatientGraphClient()
    try:
        row = upsert_quota(pg, org_id, body.monthlyLimit, org_name=body.orgName)
        return {"quota": row}
    finally:
        pg.close()


def _account_note() -> str:
    return "Azure is the whole shared account. Our number is this environment only."
