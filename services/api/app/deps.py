"""FastAPI dependencies for auth and session."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Cookie, Depends, HTTPException

from libs.auth.org_scope import CallerScope, ScopeType, resolve_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from app.services.session_store import COOKIE_NAME, load_session

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


def require_admin(scope: CallerScope = Depends(get_caller_scope_from_request)) -> CallerScope:
    """Dependency that raises 403 unless the caller is a platform admin (GAP-003)."""
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
