"""NCDA pathway-config admin router.

GET    /api/ncda/pathway-config            list all sites' bands
GET    /api/ncda/pathway-config/{site_key} read one
PUT    /api/ncda/pathway-config/{site_key} upsert one (regulatory_reviewer or administrator role)

Stores per-site typical-time bands as :NCDAPathwayConfig nodes. Defaults
load from libs.domains.ncda_pathway_config.DEFAULT_BANDS when no Neo4j
override exists yet.

Atlas trace:
  See plan stage-8-pathway-config in
  .cursor/plans/ncda_cancer_detector_ml_*.plan.md
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.ncda_pathway_config_queries import (
    GET_NCDA_PATHWAY_CONFIG,
    LIST_NCDA_PATHWAY_CONFIG,
    UPSERT_NCDA_PATHWAY_CONFIG,
)
from libs.domains.ncda_pathway_config import (
    DEFAULT_BANDS,
    PathwayBands,
    normalise_site_key,
)

router = APIRouter(prefix="/api/ncda/pathway-config", tags=["ncda-pathway-config"])

# Allowed roles for write operations on NCDA pathway config.
_WRITE_ROLES = {"regulatory_reviewer", "technical_onboarding", "administrator"}


class PathwayBandsBody(BaseModel):
    """Mutable per-site bands. site_key is taken from the path parameter."""

    ftr_to_seen_typical_max_days: int = Field(..., ge=0, le=365)
    seen_to_dx_typical_max_days: int = Field(..., ge=0, le=365)
    dx_to_treatment_typical_max_days: int = Field(..., ge=0, le=365)
    ftr_to_dx_typical_max_days: int = Field(..., ge=0, le=365)
    ftr_to_treatment_typical_max_days: int = Field(..., ge=0, le=365)


def _bands_dict(bands: PathwayBands) -> dict[str, Any]:
    return bands.to_dict() | {"updated_by": None, "updated_at": None}


def _check_write_permission(scope: CallerScope) -> None:
    """Allow administrator, regulatory_reviewer, or technical_onboarding roles."""
    if scope.is_admin:
        return
    roles = {r.lower() for r in (getattr(scope, "roles", []) or [])}
    if not (_WRITE_ROLES & roles):
        raise HTTPException(
            status_code=403,
            detail="regulatory_reviewer, technical_onboarding, or administrator role required.",
        )


@router.get("")
def list_pathway_config(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List per-site bands; merge in defaults for sites without overrides."""
    client = PatientGraphClient()
    try:
        with client.session() as s:
            stored = {row["site_key"]: dict(row) for row in s.run(LIST_NCDA_PATHWAY_CONFIG)}
    finally:
        client.close()

    items: list[dict[str, Any]] = []
    for site_key, bands in DEFAULT_BANDS.items():
        if site_key in stored:
            items.append(stored[site_key])
        else:
            items.append(_bands_dict(bands))
    for site_key, row in stored.items():
        if site_key not in DEFAULT_BANDS:
            items.append(row)
    items.sort(key=lambda x: x["site_key"])
    return {"items": items}


@router.get("/{site_key}")
def get_pathway_config(
    site_key: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    canonical = normalise_site_key(site_key)
    client = PatientGraphClient()
    try:
        with client.session() as s:
            row = s.run(GET_NCDA_PATHWAY_CONFIG, site_key=canonical).single()
            if row:
                return dict(row)
    finally:
        client.close()
    if canonical not in DEFAULT_BANDS:
        raise HTTPException(status_code=404, detail=f"Unknown site_key: {site_key}")
    return _bands_dict(DEFAULT_BANDS[canonical])


@router.put("/{site_key}")
def upsert_pathway_config(
    site_key: str,
    body: PathwayBandsBody,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _check_write_permission(scope)
    canonical = normalise_site_key(site_key)
    if not canonical:
        raise HTTPException(status_code=400, detail="site_key required")
    client = PatientGraphClient()
    try:
        with client.session() as s:
            s.run(
                UPSERT_NCDA_PATHWAY_CONFIG,
                site_key=canonical,
                ftr_to_seen_typical_max_days=body.ftr_to_seen_typical_max_days,
                seen_to_dx_typical_max_days=body.seen_to_dx_typical_max_days,
                dx_to_treatment_typical_max_days=body.dx_to_treatment_typical_max_days,
                ftr_to_dx_typical_max_days=body.ftr_to_dx_typical_max_days,
                ftr_to_treatment_typical_max_days=body.ftr_to_treatment_typical_max_days,
                updated_by=scope.email or "unknown",
            )
    finally:
        client.close()
    return {"site_key": canonical, "status": "upserted"}
