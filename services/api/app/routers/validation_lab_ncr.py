"""Validation Lab product non-conformance lookup and create.

Atlas: DI-287FFFD0
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import require_admin_or_service
from libs.atlas_qms.ncr_client import (
    NcrClientError,
    NcrNotConfigured,
    create_product_ncr,
    get_product_ncr,
    list_product_ncrs,
)
from libs.atlas_qms.ncr_shape import (
    LEO_CDS_PRODUCT_ID,
    NcrShapeError,
    build_create_description,
)
from libs.auth.org_scope import CallerScope

router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])


class CreateNcrBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    severity: str = Field(min_length=1, max_length=32)
    run_id: str = Field(default="", max_length=128)
    why: str = Field(default="", max_length=1000)


@router.get("/ncrs")
def list_ncrs(
    q: str | None = Query(default=None),
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    try:
        items = list_product_ncrs(query=str(q or "").strip())
    except NcrNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NcrClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"product_id": LEO_CDS_PRODUCT_ID, "items": items}


@router.get("/ncrs/{nc_id}")
def get_ncr(
    nc_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, str]:
    try:
        return get_product_ncr(nc_id)
    except NcrNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NcrClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/ncrs", status_code=201)
def create_ncr(
    body: CreateNcrBody,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, str]:
    description = build_create_description(
        body.description, run_id=body.run_id, why=body.why
    )
    try:
        return create_product_ncr(
            title=body.title,
            description=description,
            severity=body.severity,
        )
    except NcrShapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NcrNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NcrClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
