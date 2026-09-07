"""Merge the login organisation on azureTenantId.

Atlas trace:
  DO: DO-8E4A6AF6
  DI: DI-E6963408, DI-A482F83F
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8E4A6AF6")
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from libs.cypher.admin_queries import MERGE_ORG_BY_AZURE_TENANT
from libs.cypher.hccp_identity_queries import MERGE_USER_ON_LOGIN
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrgProvisionResult:
    ok: bool
    org_id: str | None = None
    reason: str | None = None


def org_display_name(email: str, tid: str) -> str:
    if "@" in (email or ""):
        domain = email.split("@", 1)[1].strip()
        if domain:
            return domain
    short = (tid or "").replace("-", "")[:8]
    return f"Tenant {short}" if short else "Unknown organisation"


def ensure_organization_for_tenant(
    tid: str,
    name: str,
) -> OrgProvisionResult:
    """MERGE Organization {azureTenantId}. Fail closed on empty tid or graph error."""
    cleaned = (tid or "").strip()
    if not cleaned:
        return OrgProvisionResult(ok=False, reason="empty_tid")
    display = (name or "").strip() or org_display_name("", cleaned)
    client = None
    try:
        client = PatientGraphClient()
        rows = client.run(
            MERGE_ORG_BY_AZURE_TENANT,
            azureTenantId=cleaned,
            id=cleaned,
            name=display,
            short_name=display[:30],
        )
        if not rows:
            return OrgProvisionResult(ok=False, reason="merge_failed")
        return OrgProvisionResult(ok=True, org_id=str(rows[0].get("id") or cleaned))
    except Exception as exc:
        logger.error("org.merge_failed tid=%s err=%s", cleaned, exc)
        return OrgProvisionResult(ok=False, reason="merge_failed")
    finally:
        if client is not None:
            client.close()


@dataclass(frozen=True)
class UserProvisionResult:
    ok: bool
    email: str | None = None
    reason: str | None = None


def _login_email(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if not cleaned or cleaned == "unknown":
        return ""
    return cleaned


def ensure_user_for_login(email: str, name: str) -> UserProvisionResult:
    """MERGE User {email}. Admin is false on create only. Fail closed."""
    cleaned = _login_email(email)
    if not cleaned:
        return UserProvisionResult(ok=False, reason="empty_email")
    display = (name or "").strip() or cleaned
    client = None
    try:
        client = PatientGraphClient()
        rows = client.run(
            MERGE_USER_ON_LOGIN,
            email=cleaned,
            name=display,
            id=str(uuid.uuid4()),
        )
        if not rows:
            return UserProvisionResult(ok=False, reason="merge_failed")
        return UserProvisionResult(ok=True, email=str(rows[0].get("email") or cleaned))
    except Exception as exc:
        logger.error("user.merge_failed email=%s err=%s", cleaned, exc)
        return UserProvisionResult(ok=False, reason="merge_failed")
    finally:
        if client is not None:
            client.close()
