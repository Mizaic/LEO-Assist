"""Who may read the existing organisation and service catalog.

Teach this form reuses the tenant-drawer list. Form teachers need that
read path even when they are not organisation administrators.

Atlas trace: DI-26546721, UN-3B25A20E
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.deps import get_session_data
from libs.auth.org_scope import CallerScope, resolve_caller_scope
from libs.neo4j_client.client import PatientGraphClient

FORM_TEACHER_ROLES = (
    "validation",
    "operations_manager",
    "clinician_admin",
    "administrator",
)


def require_org_catalog_reader(
    session_data: dict = Depends(get_session_data),
) -> CallerScope:
    """Return a caller who may list organisations and services."""
    caller_email = (session_data.get("email") or "").strip().lower()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if session_data.get("is_platform_admin") is True:
        return _unrestricted(caller_email)
    selected = session_data.get("selected_role") or ""
    client = PatientGraphClient()
    try:
        if _has_org_admin_role(client, caller_email):
            return resolve_caller_scope(client, caller_email)
        if selected in FORM_TEACHER_ROLES:
            scope = resolve_caller_scope(client, caller_email)
            return scope if scope.org_ids else _unrestricted(caller_email)
    finally:
        client.close()
    raise HTTPException(
        status_code=403,
        detail="You cannot load the organisation list for this form.",
    )


def _unrestricted(email: str) -> CallerScope:
    return CallerScope(
        email=email,
        is_admin=True,
        org_ids=[],
        scope_type=None,
        primary_org_id=None,
    )


def _has_org_admin_role(client: PatientGraphClient, email: str) -> bool:
    rows = client.run(
        "MATCH (u:User {email: $email})-[:IS_MEMBER_OF]->"
        "(:Group)-[:HAS_ROLE]->(role:Role) "
        "WHERE role.name = 'organization_administrator' "
        "   OR role.id = 'organization_administrator' "
        "RETURN 1 AS ok LIMIT 1",
        email=email,
    )
    return bool(rows)
