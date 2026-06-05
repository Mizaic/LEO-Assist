"""FastAPI dependencies for auth and session.

Atlas trace:
  DO: DO-DB7F8D52
  DI: DI-4DBE1A18, DI-87CCCB18
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-DB7F8D52")
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated, Literal

from fastapi import Cookie, Depends, HTTPException, Request

from libs.audit.security_log import emit_authz_denied
from libs.auth.org_scope import CallerScope, ScopeType, resolve_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from app.services.session_store import COOKIE_NAME, load_session

SERVICE_ACCOUNT_EMAIL = "service-account@leo.local"

# Mapping of org type → permitted child org types for delegated onboarding.
# A Cancer Alliance admin can create ICBs; an ICB admin can create PCNs or GPs, etc.
_PERMITTED_CHILD_TYPES: dict[str | None, list[str]] = {
    "alliance": ["icb"],
    "icb": ["pcn", "gp"],
    "pcn": ["gp"],
    "gp": [],
    None: ["alliance", "icb", "pcn", "gp"],  # platform admin: unrestricted
}


def permitted_child_types(scope_type: ScopeType | None) -> list[str]:
    """Return the org types an org admin of this scope_type may create as children."""
    return _PERMITTED_CHILD_TYPES.get(scope_type, [])


def get_session_data(
    leo_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> dict:
    """Dependency that returns session data or raises 401."""
    if not leo_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = load_session(leo_session)
    if not data:
        raise HTTPException(status_code=401, detail="Session expired")
    return data


def get_access_token(session_data: dict = Depends(get_session_data)) -> str:
    """Dependency that returns the access token from session."""
    token = session_data.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No access token")
    return token


def get_user_email(session_data: dict = Depends(get_session_data)) -> str:
    """Dependency that returns the normalized user email from session."""
    email = (session_data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No user email in session")
    return email


def get_caller_scope_from_request(
    session_data: dict = Depends(get_session_data),
) -> CallerScope:
    """Resolve caller org scope from the authenticated session cookie only.

    GAP-001: X-User-Email header and ?email= query param removed.
    Caller identity is taken solely from the server-side session to prevent
    header spoofing.

    Platform admin status is taken from the session (set at login from the
    Analytics API / Neo4j). For non-admin users, org scope is resolved live
    from Neo4j so org membership changes take effect immediately.
    """
    caller_email = (session_data.get("email") or "").strip().lower()
    if not caller_email:
        raise HTTPException(status_code=401, detail="No user email in session")

    # Fast path: session records admin status set at login time.
    if session_data.get("is_platform_admin") is True:
        return CallerScope(
            email=caller_email,
            is_admin=True,
            org_ids=[],
            scope_type=None,
            primary_org_id=None,
        )

    client = PatientGraphClient()
    try:
        return resolve_caller_scope(client, caller_email)
    finally:
        client.close()


def require_admin(
    request: Request,
    scope: CallerScope = Depends(get_caller_scope_from_request),
) -> CallerScope:
    """Dependency that raises 403 unless the caller is a platform admin (GAP-003)."""
    if not scope.is_admin:
        client_ip = request.client.host if request.client else "unknown"
        emit_authz_denied(
            email=scope.email,
            ip=client_ip,
            route=str(request.url.path),
            reason="not_platform_admin",
        )
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return scope


def _service_account_scope() -> CallerScope:
    """Synthetic admin scope for inter-service callers that pass service auth."""
    return CallerScope(
        email=SERVICE_ACCOUNT_EMAIL,
        is_admin=True,
        org_ids=[],
        scope_type=None,
        primary_org_id=None,
    )


def _service_token_scope_or_none(request: Request) -> CallerScope | None:
    """Return a service-account scope if a valid SERVICE_AUTH_SECRET token is
    present, raise 401 if a Bearer token is supplied but wrong, otherwise
    return None so the caller can fall back to the session-cookie path.

    When SERVICE_AUTH_SECRET is unset (local dev), no Bearer header path is
    accepted -- callers must use the session cookie. This matches the
    existing security posture in libs/auth/service_auth.py while keeping the
    admin UI working unchanged.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    expected = os.environ.get("SERVICE_AUTH_SECRET", "")
    if not expected:
        return None
    provided = auth_header.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid service auth token")
    return _service_account_scope()


def require_admin_or_service(
    request: Request,
    leo_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> CallerScope:
    """Allow either an admin session OR a valid SERVICE_AUTH_SECRET Bearer token.

    Used on endpoints that can legitimately be called from the admin UI
    (session cookie) and from another internal service over ACA's internal
    network (e.g. terminology-api -> /guidance/test-patients/replay after a
    successful guideline compile, see DI-LEO-AI-167).

    Behaviour:
      - Bearer token + SERVICE_AUTH_SECRET configured: validate timing-safe,
        return synthetic admin scope on match; 401 on mismatch.
      - Bearer token without configured secret (local dev): ignored; falls
        through to the session check.
      - Otherwise: identical to require_admin (cookie-backed admin scope).
    """
    service_scope = _service_token_scope_or_none(request)
    if service_scope is not None:
        return service_scope

    if not leo_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = load_session(leo_session)
    if not data:
        raise HTTPException(status_code=401, detail="Session expired")
    caller_email = (data.get("email") or "").strip().lower()
    if not caller_email:
        raise HTTPException(status_code=401, detail="No user email in session")
    if data.get("is_platform_admin") is True:
        return CallerScope(
            email=caller_email,
            is_admin=True,
            org_ids=[],
            scope_type=None,
            primary_org_id=None,
        )
    client = PatientGraphClient()
    try:
        scope = resolve_caller_scope(client, caller_email)
    finally:
        client.close()
    if not scope.is_admin:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return scope


def _has_org_admin_role(client: PatientGraphClient, email: str) -> bool:
    """Return True if the practitioner has the org_admin role for any org."""
    rows = client.run(
        "MATCH (pr:Practitioner {email: $email})-[r:HAS_ROLE]->(role:Role {name: 'org_admin'}) "
        "RETURN r.org_id AS org_id LIMIT 1",
        email=email,
    )
    return bool(rows)


def require_admin_or_org_admin(
    session_data: dict = Depends(get_session_data),
) -> CallerScope:
    """Dependency that passes for platform admins or org_admin role holders.

    Platform admins receive an unrestricted CallerScope (org_ids=[]).
    Org admins receive a scope limited to their WORKS_AT hierarchy — list
    endpoints must filter by scope.org_ids when is_admin is False.
    """
    caller_email = (session_data.get("email") or "").strip().lower()
    if not caller_email:
        raise HTTPException(status_code=401, detail="No user email in session")

    if session_data.get("is_platform_admin") is True:
        return CallerScope(
            email=caller_email,
            is_admin=True,
            org_ids=[],
            scope_type=None,
            primary_org_id=None,
        )

    client = PatientGraphClient()
    try:
        if not _has_org_admin_role(client, caller_email):
            raise HTTPException(
                status_code=403,
                detail="Platform admin or org admin access required",
            )
        return resolve_caller_scope(client, caller_email)
    finally:
        client.close()
