"""Onboarding router.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

POST /onboard — provision a new organisation and its primary user in a single
atomic-ish saga.  Callable by platform admins (any org type) or org admins
(one level below their own org type only).

Saga steps (all idempotent; failures abort with 409 / 502):
  1. ODS validation — confirm ODS code exists and matches the declared type
  2. Neo4j — create org node + subscription node, link to parent
  3. Neo4j -- create User/Practitioner + organization_administrator via group
  4. Email  — send onboarding invite via Microsoft Graph
  5. Neo4j  — flip onboarding_status → active
  6. Audit  — emit onboarding event
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.deps import require_admin_or_org_admin, permitted_child_types
from app.services import mail as mail_svc
from libs.audit.audit_emitter import emit_application_event
from libs.auth.org_scope import CallerScope
from libs.cypher import admin_queries as aq
from libs.neo4j_client.client import PatientGraphClient
from libs.ods.client import OdsApiError, OdsNotFoundError, OdsRateLimitError, get_org

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboard", tags=["onboarding"])

_ORG_TYPE_TO_CREATE_QUERY = {
    "gp": aq.CREATE_ORG_GP,
    "icb": aq.CREATE_ORG_ICB,
    "alliance": aq.CREATE_ORG_ALLIANCE,
    "pcn": aq.CREATE_ORG_PCN,
    "service_provider": aq.CREATE_ORG_SERVICE_PROVIDER,
}

_ORG_TYPE_LABEL = {
    "gp": "GPPractice",
    "icb": "ICB",
    "alliance": "CancerAlliance",
    "pcn": "PCN",
    "service_provider": "ServiceProvider",
}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AddressPayload(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None


class SubscriptionPayload(BaseModel):
    tier: str  # "cancer_alliance" | "icb" | "pcn"
    credits: Optional[int] = None
    expires_at: Optional[str] = None  # ISO 8601
    purchase_ref: Optional[str] = None


class OrgPayload(BaseModel):
    name: str
    type: str  # "gp" | "icb" | "alliance" | "pcn"
    ods_code: str
    parent_org_id: Optional[str] = None
    region: Optional[str] = None
    address: Optional[AddressPayload] = None
    subscription: Optional[SubscriptionPayload] = None
    entra_tenant_id: Optional[str] = None  # set when known up-front; otherwise filled on first login

    @field_validator("entra_tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # Accept full GUID (8-4-4-4-12) or 32-char hex.
        compact = v.replace("-", "").lower()
        if len(compact) != 32 or any(c not in "0123456789abcdef" for c in compact):
            raise ValueError("entra_tenant_id must be a GUID")
        return v.lower()


class PrimaryUserPayload(BaseModel):
    email: str
    given_name: str
    family_name: str
    job_title: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@", 1)[-1]:
            raise ValueError("Invalid email address")
        return v


class OnboardRequest(BaseModel):
    organisation: OrgPayload
    primary_user: PrimaryUserPayload


class OnboardResponse(BaseModel):
    org_id: str
    user_email: str
    onboarding_status: str
    message: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=OnboardResponse, status_code=201)
def onboard(
    body: OnboardRequest,
    scope: CallerScope = Depends(require_admin_or_org_admin),
) -> OnboardResponse:
    """Provision a new organisation and its primary user.

    Platform admins may onboard any org type.
    Org admins may only onboard org types one level below their own.
    """
    org = body.organisation
    user = body.primary_user
    full_name = f"{user.given_name} {user.family_name}".strip()
    now_iso = datetime.now(timezone.utc).isoformat()

    # -- Permission check: org admins may only create permitted child types ----
    if not scope.is_admin:
        allowed = permitted_child_types(scope.scope_type)
        if org.type not in allowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Org admin of type '{scope.scope_type}' may not create "
                    f"'{org.type}' organisations. Allowed: {allowed}"
                ),
            )
        # Org admin must link child to their own org (cannot specify arbitrary parent)
        if (
            org.parent_org_id
            and scope.primary_org_id
            and org.parent_org_id != scope.primary_org_id
        ):
            raise HTTPException(
                status_code=403,
                detail="Org admin can only add sub-organisations to their own org",
            )
        # Default parent to caller's org if not provided
        if not org.parent_org_id:
            org.parent_org_id = scope.primary_org_id

    # -- Step 1: ODS validation -----------------------------------------------
    try:
        ods_org = get_org(org.ods_code)
    except OdsNotFoundError:
        raise HTTPException(
            status_code=422, detail=f"ODS code '{org.ods_code}' not found in NHS ODS"
        )
    except OdsRateLimitError:
        raise HTTPException(
            status_code=502, detail="NHS ODS API rate limited — please retry shortly"
        )
    except OdsApiError as exc:
        logger.warning("ODS API error during onboarding: %s", exc)
        raise HTTPException(status_code=502, detail=f"ODS API error: {exc}")

    if ods_org.status != "Active":
        raise HTTPException(
            status_code=422,
            detail=f"ODS code '{org.ods_code}' is not Active in NHS ODS (status: {ods_org.status})",
        )

    client = PatientGraphClient()
    try:
        # -- Step 2a: check for duplicate ODS code ----------------------------
        existing = client.run(
            "MATCH (o:Organization {odsCode: $ods_code}) RETURN o.id AS id LIMIT 1",
            ods_code=org.ods_code.upper(),
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"An organisation with ODS code '{org.ods_code}' already exists",
            )

        # -- Step 2b: create organisation node --------------------------------
        create_query = _ORG_TYPE_TO_CREATE_QUERY.get(org.type)
        if not create_query:
            raise HTTPException(status_code=422, detail=f"Unknown org type: {org.type}")

        org_id = str(uuid.uuid4())
        client.run(
            create_query,
            id=org_id,
            name=org.name,
            ods_code=org.ods_code.upper(),
            short_name=org.name[:30],
            entra_tenant_id=org.entra_tenant_id or "",
            onboarding_status="pending",
        )
        logger.info(
            "[Onboarding] Created org %s (%s, type=%s)", org_id, org.name, org.type
        )

        # -- Step 2c: link to parent org --------------------------------------
        if org.parent_org_id:
            if org.type == "icb":
                client.run(
                    aq.LINK_ORG_PART_OF_ALLIANCE,
                    icb_id=org_id,
                    alliance_id=org.parent_org_id,
                )
            elif org.type == "gp" and _is_pcn(client, org.parent_org_id):
                client.run(
                    aq.LINK_GP_TO_PCN,
                    gp_id=org_id,
                    pcn_id=org.parent_org_id,
                    effective_from=now_iso,
                )
            else:
                client.run(
                    aq.LINK_ORG_COMMISSIONED_BY,
                    child_id=org_id,
                    parent_id=org.parent_org_id,
                )

        # -- Step 2d: create subscription node --------------------------------
        if org.subscription:
            sub = org.subscription
            client.run(
                aq.CREATE_SUBSCRIPTION,
                id=str(uuid.uuid4()),
                org_id=org_id,
                tier=sub.tier,
                seat_count=0,
                credits_purchased=sub.credits or 0,
                purchase_ref=sub.purchase_ref or "",
                expires_at=sub.expires_at or "",
            )

        # -- Step 3: create primary user Practitioner -------------------------
        practitioner_id = str(uuid.uuid4())
        email_lower = str(user.email).lower().strip()
        client.run(
            aq.CREATE_PRACTITIONER,
            email=email_lower,
            name=full_name,
            is_platform_admin=False,
            id=practitioner_id,
            org_ids=[org_id],
        )
        client.run(
            aq.ASSIGN_USER_ROLE,
            email=email_lower,
            role_name="organization_administrator",
            org_id=org_id,
        )
        logger.info(
            "[Onboarding] Created primary user %s for org %s", email_lower, org_id
        )

    except HTTPException:
        client.close()
        raise
    except Exception as exc:
        client.close()
        logger.error("[Onboarding] Neo4j error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Database error during onboarding"
        ) from exc

    # -- Step 4: send invite email (non-fatal) --------------------------------
    try:
        mail_svc.send_onboarding_invite_email(
            to_email=email_lower,
            to_name=full_name,
            org_name=org.name,
            org_type=org.type,
        )
        logger.info("[Onboarding] Invite email sent to %s", email_lower)
    except Exception as exc:
        logger.warning("[Onboarding] Invite email failed (non-fatal): %s", exc)

    # -- Step 5: flip onboarding_status to active -----------------------------
    try:
        client.run(aq.UPDATE_ORG, id=org_id, updates={"onboarding_status": "active"})
    except Exception as exc:
        logger.warning("[Onboarding] Failed to set onboarding_status=active: %s", exc)
    finally:
        client.close()

    # -- Step 6: emit audit event ---------------------------------------------
    try:
        emit_application_event(
            outcome="0",
            agent_email=scope.email,
            description=f"org_onboarded org_id={org_id} org_name={org.name} org_type={org.type} ods_code={org.ods_code} primary_user={email_lower}",
            source_service="onboarding",
        )
    except Exception as exc:
        logger.warning("[Onboarding] Audit emit failed (non-fatal): %s", exc)

    return OnboardResponse(
        org_id=org_id,
        user_email=email_lower,
        onboarding_status="active",
        message=f"Organisation '{org.name}' onboarded successfully. Invite sent to {email_lower}.",
    )


def _is_pcn(client: PatientGraphClient, org_id: str) -> bool:
    """Return True if the given org_id belongs to a PCN node."""
    rows = client.run(
        "MATCH (o:PCN {id: $id}) RETURN o.id AS id LIMIT 1",
        id=org_id,
    )
    return bool(rows)
