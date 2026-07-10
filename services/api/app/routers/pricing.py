"""Pricing, margin and discount management router.

Atlas trace:
  DO: DO-FD338D48
  DI: DI-21FD1EC2
  UN: UN-9828175D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-FD338D48")

(2026-07 cost/spend user-need review: the previous header cited
DO-EC41233C/DI-9D0DF618, which do not exist in Atlas -- the same phantom
pair is also cited by app/routers/model_configs.py and
app/routers/terminology.py, and was never a valid trace for any of the
three. This file's header is now corrected. The other two still need
their own investigation and are tracked as a follow-up, not fixed here.)

All endpoints require the 'admin' permission.

Routes
------
GET  /pricing/config                           — global margin config
PUT  /pricing/config                           — update global margin
GET  /pricing/orgs                             — per-tenant spend with pricing applied
GET  /pricing/orgs/{org_id}/discounts          — list discounts for a tenant
POST /pricing/orgs/{org_id}/discounts          — add a discount
DELETE /pricing/discounts/{discount_id}        — deactivate a discount
GET  /pricing/platform-spend                   — non-patient platform spend

Pricing formula
---------------
  list_price  = raw_cost / (1 - target_margin)
  billable    = list_price × (1 - Σ active_discount_rates)
  gross_margin = (list_price - raw_cost) / list_price  [== target_margin when no discount]
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.pricing_queries import (
    CREATE_ORG_DISCOUNT,
    DEACTIVATE_ORG_DISCOUNT,
    DELETE_ORG_DISCOUNT,
    GET_ACTIVE_DISCOUNT_RATE,
    GET_PRICING_CONFIG,
    LIST_ORG_DISCOUNTS,
    ORG_SPEND_SUMMARY,
    PLATFORM_SPEND_SUMMARY,
    UPSERT_PRICING_CONFIG,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pricing", tags=["pricing"])

DEFAULT_TARGET_MARGIN = 0.75  # 75% gross margin


# ── Guards ────────────────────────────────────────────────────────────────────


def _require_admin(scope: CallerScope) -> None:
    if not scope.is_admin:
        raise HTTPException(403, "Admin permission required")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _apply_pricing(
    raw_cost: float,
    target_margin: float,
    total_discount_rate: float,
) -> dict[str, float]:
    """Compute list price, billable amount, and effective margin."""
    if target_margin >= 1.0:
        target_margin = 0.999
    list_price = raw_cost / (1.0 - target_margin) if raw_cost > 0 else 0.0
    capped_discount = min(total_discount_rate, 1.0)
    billable = list_price * (1.0 - capped_discount)
    effective_margin = (billable - raw_cost) / billable if billable > 0 else 0.0
    return {
        "rawCostUsd": round(raw_cost, 6),
        "listPriceUsd": round(list_price, 6),
        "discountRate": round(capped_discount, 4),
        "billableUsd": round(billable, 6),
        "grossMargin": round(effective_margin, 4),
        "targetMargin": round(target_margin, 4),
    }


def _get_margin(kg: CodingGraphClient) -> float:
    """Return the stored target margin, or the default if not configured."""
    with kg.session() as s:
        row = s.run(GET_PRICING_CONFIG).single()
    return float(row["target_margin"]) if row else DEFAULT_TARGET_MARGIN


# ── Pydantic models ───────────────────────────────────────────────────────────


class MarginConfigUpdate(BaseModel):
    targetMargin: float = Field(
        ..., ge=0.0, lt=1.0, description="Gross margin 0.0–0.99, e.g. 0.75 = 75%"
    )


class DiscountCreate(BaseModel):
    description: str = Field(..., min_length=1)
    rate: float = Field(
        ..., ge=0.0, le=1.0, description="Discount rate 0.0–1.0, e.g. 0.20 = 20% off"
    )
    type: str = Field(..., description="'promo' or 'contract'")
    validFrom: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    validTo: str | None = Field(
        None, description="ISO datetime or null for perpetual (life of contract)"
    )

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in ("promo", "contract"):
            raise ValueError("type must be 'promo' or 'contract'")
        return v


# ── GET /pricing/config ───────────────────────────────────────────────────────


@router.get("/config")
def get_pricing_config(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    kg = CodingGraphClient()
    try:
        margin = _get_margin(kg)
        with kg.session() as s:
            row = s.run(GET_PRICING_CONFIG).single()
        return {
            "targetMargin": margin,
            "updatedBy": row["updated_by"] if row else None,
            "updatedAt": row["updated_at"] if row else None,
            "isDefault": row is None,
        }
    finally:
        kg.close()


# ── PUT /pricing/config ───────────────────────────────────────────────────────


@router.put("/config")
def update_pricing_config(
    body: MarginConfigUpdate,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    kg = CodingGraphClient()
    try:
        with kg.session() as s:
            s.run(
                UPSERT_PRICING_CONFIG,
                target_margin=body.targetMargin,
                updated_by=scope.email or "admin",
            )
        logger.info(
            "PricingConfig updated: margin=%.2f%% by %s",
            body.targetMargin * 100,
            scope.email,
        )
        return {"targetMargin": body.targetMargin, "status": "updated"}
    finally:
        kg.close()


# ── GET /pricing/orgs ─────────────────────────────────────────────────────────


@router.get("/orgs")
def get_org_spend(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Per-tenant spend with margin and discounts applied. Admin only."""
    _require_admin(scope)

    kg = CodingGraphClient()
    pg = PatientGraphClient()
    try:
        target_margin = _get_margin(kg)

        # Aggregate raw spend per org from Patient Graph
        with pg.session() as s:
            raw_rows = s.run(
                ORG_SPEND_SUMMARY, from_date=from_date, to_date=to_date
            ).data()

        orgs = []
        for row in raw_rows:
            org_id = row.get("orgId", "")
            raw_cost = float(row.get("rawCostUsd") or 0)

            # Look up active discounts for this org from Knowledge Graph
            with kg.session() as s:
                disc = s.run(GET_ACTIVE_DISCOUNT_RATE, org_id=org_id).single()
            total_discount = float(disc["total_discount_rate"]) if disc else 0.0
            active_discounts = disc["active_discounts"] if disc else []

            pricing = _apply_pricing(raw_cost, target_margin, total_discount)
            orgs.append(
                {
                    "orgId": org_id,
                    "orgName": row.get("orgName", ""),
                    "runCount": int(row.get("runCount") or 0),
                    "inputTokens": int(row.get("inputTokens") or 0),
                    "outputTokens": int(row.get("outputTokens") or 0),
                    "cachedTokens": int(row.get("cachedTokens") or 0),
                    "activeDiscounts": active_discounts,
                    **pricing,
                }
            )

        platform_raw = sum(o["rawCostUsd"] for o in orgs)
        platform_billable = sum(o["billableUsd"] for o in orgs)

        return {
            "orgs": orgs,
            "targetMargin": target_margin,
            "totals": {
                "rawCostUsd": round(platform_raw, 6),
                "billableUsd": round(platform_billable, 6),
                "orgCount": len(orgs),
            },
        }
    finally:
        kg.close()
        pg.close()


# ── GET /pricing/orgs/{org_id}/discounts ─────────────────────────────────────


@router.get("/orgs/{org_id}/discounts")
def list_org_discounts(
    org_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    kg = CodingGraphClient()
    try:
        with kg.session() as s:
            rows = s.run(LIST_ORG_DISCOUNTS, org_id=org_id).data()
        return {"orgId": org_id, "discounts": rows}
    finally:
        kg.close()


# ── POST /pricing/orgs/{org_id}/discounts ────────────────────────────────────


@router.post("/orgs/{org_id}/discounts", status_code=201)
def create_org_discount(
    org_id: str,
    body: DiscountCreate,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    kg = CodingGraphClient()
    try:
        discount_id = str(uuid.uuid4())
        with kg.session() as s:
            s.run(
                CREATE_ORG_DISCOUNT,
                discount_id=discount_id,
                org_id=org_id,
                description=body.description,
                rate=body.rate,
                type=body.type,
                valid_from=body.validFrom,
                valid_to=body.validTo,
                created_by=scope.email or "admin",
            )
        logger.info(
            "OrgDiscount created: org=%s rate=%.0f%% type=%s by %s",
            org_id,
            body.rate * 100,
            body.type,
            scope.email,
        )
        return {"discountId": discount_id, "orgId": org_id, "status": "created"}
    finally:
        kg.close()


# ── DELETE /pricing/discounts/{discount_id} ───────────────────────────────────


@router.delete("/discounts/{discount_id}")
def delete_org_discount(
    discount_id: str,
    permanent: bool = Query(
        False, description="True = hard delete; False = deactivate only"
    ),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    _require_admin(scope)
    kg = CodingGraphClient()
    try:
        with kg.session() as s:
            if permanent:
                result = s.run(DELETE_ORG_DISCOUNT, discount_id=discount_id).single()
                deleted = result["deleted"] if result else 0
                if not deleted:
                    raise HTTPException(404, f"Discount {discount_id!r} not found")
            else:
                result = s.run(
                    DEACTIVATE_ORG_DISCOUNT, discount_id=discount_id
                ).single()
                if not result:
                    raise HTTPException(404, f"Discount {discount_id!r} not found")
        action = "deleted" if permanent else "deactivated"
        logger.info("OrgDiscount %s: %s by %s", action, discount_id, scope.email)
        return {"discountId": discount_id, "status": action}
    finally:
        kg.close()


# ── GET /pricing/platform-spend ───────────────────────────────────────────────


@router.get("/platform-spend")
def get_platform_spend(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Non-patient-linked spend (training runs, verification, gold dataset).
    These are platform operating costs, not chargeable to tenants."""
    _require_admin(scope)
    pg = PatientGraphClient()
    kg = CodingGraphClient()
    try:
        with pg.session() as s:
            rows = s.run(
                PLATFORM_SPEND_SUMMARY, from_date=from_date, to_date=to_date
            ).data()

        target_margin = _get_margin(kg)
        total_raw = sum(float(r.get("rawCostUsd") or 0) for r in rows)
        result = []
        for row in rows:
            raw = float(row.get("rawCostUsd") or 0)
            result.append(
                {
                    "eventType": row.get("eventType", ""),
                    "runCount": int(row.get("runCount") or 0),
                    "inputTokens": int(row.get("inputTokens") or 0),
                    "outputTokens": int(row.get("outputTokens") or 0),
                    "cachedTokens": int(row.get("cachedTokens") or 0),
                    "rawCostUsd": round(raw, 6),
                }
            )

        return {
            "breakdown": result,
            "targetMargin": target_margin,
            "totals": {
                "rawCostUsd": round(total_raw, 6),
                "listPriceUsd": round(
                    total_raw / (1.0 - target_margin) if total_raw > 0 else 0, 6
                ),
                "note": "Platform spend is a cost-centre — not billed to tenants.",
            },
        }
    finally:
        pg.close()
        kg.close()
