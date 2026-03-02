"""Admin router for tenant management.

All endpoints require platform admin (Depends(require_admin)).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import require_admin
from app.services import mail as mail_svc
from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient
from libs.cypher import admin_queries as aq
from app.services.session_store import (
    delete_all_sessions,
    delete_session,
    delete_sessions_by_email,
    list_all_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _client() -> PatientGraphClient:
    return PatientGraphClient()


# ------------------------------------------------------------------
# Request/response models
# ------------------------------------------------------------------


class CreateOrgBody(BaseModel):
    type: str  # gp | icb | alliance
    name: str
    ods_code: Optional[str] = None
    short_name: Optional[str] = None
    parent_id: Optional[str] = None
    alliance_id: Optional[str] = None


class PatchOrgBody(BaseModel):
    name: Optional[str] = None
    ods_code: Optional[str] = None
    short_name: Optional[str] = None


class LinkOrgBody(BaseModel):
    link_type: str  # commissioned_by | part_of_alliance
    parent_id: str
    child_id: Optional[str] = None
    icb_id: Optional[str] = None
    alliance_id: Optional[str] = None


class CreateUserBody(BaseModel):
    email: str
    name: str
    is_platform_admin: bool = False
    org_ids: list[str] = []


class PatchUserBody(BaseModel):
    name: Optional[str] = None
    is_platform_admin: Optional[bool] = None
    org_ids: Optional[list[str]] = None


class AssignRoleBody(BaseModel):
    role_name: str
    org_id: Optional[str] = None


class CreateGroupBody(BaseModel):
    name: str
    description: Optional[str] = None
    org_id: Optional[str] = None


class PatchGroupBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddGroupMemberBody(BaseModel):
    email: str


class PatchAuthConfigBody(BaseModel):
    session_ttl_hours: Optional[int] = None
    idle_timeout_minutes: Optional[int] = None
    cookie_secure: Optional[bool] = None
    require_mfa: Optional[bool] = None


# ------------------------------------------------------------------
# Organisation endpoints
# ------------------------------------------------------------------


@router.get("/orgs")
async def list_orgs(
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all orgs with type, ODS code, patient count."""
    client = _client()
    try:
        rows = client.run(aq.LIST_ORGS)
        return [_row_to_org(r) for r in rows]
    finally:
        client.close()


def _row_to_org(r: dict) -> dict:
    # Neo4j returns labels as a list; a node can carry multiple labels.
    # The Cypher already computes org_type using label + relationship context.
    org_type = r.get("org_type") or "organization"
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "odsCode": r.get("odsCode"),
        "short_name": r.get("short_name"),
        "type": org_type,
        "labels": r.get("labels") or [],
        "patient_count": r.get("patient_count", 0),
        "parent_id": r.get("parent_id"),
        "parent_name": r.get("parent_name"),
        "alliance_id": r.get("alliance_id"),
        "alliance_name": r.get("alliance_name"),
    }


@router.post("/orgs")
async def create_org(
    body: CreateOrgBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create org (type: gp/icb/alliance)."""
    org_id = str(uuid.uuid4())
    short_name = body.short_name or body.name[:30] if body.name else ""
    client = _client()
    try:
        if body.type == "gp":
            client.run(
                aq.CREATE_ORG_GP,
                id=org_id,
                name=body.name,
                ods_code=body.ods_code or "",
                short_name=short_name,
            )
        elif body.type == "icb":
            client.run(
                aq.CREATE_ORG_ICB,
                id=org_id,
                name=body.name,
                ods_code=body.ods_code or "",
                short_name=short_name,
            )
        elif body.type == "alliance":
            client.run(
                aq.CREATE_ORG_ALLIANCE,
                id=org_id,
                name=body.name,
                ods_code=body.ods_code or "",
                short_name=short_name,
            )
        else:
            raise HTTPException(400, f"Unknown org type: {body.type}")

        if body.parent_id and body.type == "gp":
            client.run(
                aq.LINK_ORG_COMMISSIONED_BY,
                child_id=org_id,
                parent_id=body.parent_id,
            )
        if body.alliance_id and body.type == "icb":
            client.run(
                aq.LINK_ORG_PART_OF_ALLIANCE,
                icb_id=org_id,
                alliance_id=body.alliance_id,
            )
        return {"id": org_id}
    finally:
        client.close()


@router.patch("/orgs/{org_id}")
async def patch_org(
    org_id: str,
    body: PatchOrgBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Update org name, odsCode, short_name."""
    updates = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None
    }
    if not updates:
        return {"id": org_id}
    client = _client()
    try:
        client.run(aq.UPDATE_ORG, id=org_id, updates=updates)
        return {"id": org_id}
    finally:
        client.close()


@router.delete("/orgs/{org_id}")
async def delete_org(
    org_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete org. Rejects if patients linked."""
    client = _client()
    try:
        rows = client.run(aq.DELETE_ORG, id=org_id)
        deleted = rows[0].get("deleted", 0) if rows else 0
        if deleted == 0:
            raise HTTPException(
                400, "Cannot delete: org has linked patients or not found"
            )
        return {"deleted": org_id}
    finally:
        client.close()


@router.post("/orgs/{org_id}/link")
async def link_org(
    org_id: str,
    body: LinkOrgBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Set COMMISSIONED_BY or PART_OF_ALLIANCE hierarchy."""
    client = _client()
    try:
        if body.link_type == "commissioned_by":
            client.run(
                aq.LINK_ORG_COMMISSIONED_BY,
                child_id=org_id,
                parent_id=body.parent_id,
            )
        elif body.link_type == "part_of_alliance":
            client.run(
                aq.LINK_ORG_PART_OF_ALLIANCE,
                icb_id=org_id,
                alliance_id=body.parent_id,
            )
        else:
            raise HTTPException(400, f"Unknown link_type: {body.link_type}")
        return {"id": org_id}
    finally:
        client.close()


# ------------------------------------------------------------------
# User endpoints
# ------------------------------------------------------------------


@router.get("/users")
async def list_users(
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List practitioners with last_seen, roles, orgs."""
    client = _client()
    try:
        rows = client.run(aq.LIST_PRACTITIONERS)
        sessions = list_all_sessions()
        email_to_sessions = {}
        for s in sessions:
            e = (s.get("email") or "").strip().lower()
            if e:
                email_to_sessions.setdefault(e, []).append(s)
        out = []
        for r in rows:
            email = (r.get("email") or "").strip().lower()
            user_sessions = email_to_sessions.get(email, [])
            out.append(
                {
                    "id": r.get("id"),
                    "email": email,
                    "name": r.get("name"),
                    "is_platform_admin": r.get("is_platform_admin", False),
                    "org_ids": r.get("org_ids") or [],
                    "org_names": r.get("org_names") or [],
                    "roles": r.get("roles") or [],
                    "last_seen_at": _neo4j_datetime_str(r.get("last_seen_at")),
                    "invited_at": _neo4j_datetime_str(r.get("invited_at")),
                    "active_sessions_count": len(user_sessions),
                }
            )
        return out
    finally:
        client.close()


def _neo4j_datetime_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)


@router.post("/users")
async def create_user(
    body: CreateUserBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create/invite practitioner (MERGE)."""
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(400, "email required")
    client = _client()
    try:
        client.run(
            aq.CREATE_PRACTITIONER,
            email=email,
            name=body.name,
            is_platform_admin=body.is_platform_admin,
            id=str(uuid.uuid4()),
            org_ids=body.org_ids or [],
        )
    finally:
        client.close()

    try:
        mail_svc.send_invite_email(email, body.name or email, _scope.name or "An admin")
    except Exception as exc:
        logger.warning("Invite email failed for %s: %s", email, exc)

    return {"email": email}


@router.patch("/users/{email}")
async def patch_user(
    email: str,
    body: PatchUserBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Update name, is_platform_admin, orgs."""
    email = email.strip().lower()
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.is_platform_admin is not None:
        updates["is_platform_admin"] = body.is_platform_admin
    org_ids = body.org_ids
    client = _client()
    try:
        if org_ids is None:
            rows = client.run(aq.GET_PRACTITIONER_ORG_IDS, email=email)
            org_ids = rows[0]["org_ids"] if rows else []
        client.run(
            aq.UPDATE_PRACTITIONER,
            email=email,
            updates=updates,
            org_ids=org_ids,
        )
        return {"email": email}
    finally:
        client.close()


@router.delete("/users/{email}")
async def delete_user(
    email: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Detach and deactivate (does not delete node)."""
    email = email.strip().lower()
    client = _client()
    try:
        client.run(aq.DEACTIVATE_PRACTITIONER, email=email)
        return {"email": email}
    finally:
        client.close()


@router.post("/users/{email}/logout")
async def force_logout_user(
    email: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Force logout - delete all Redis sessions for that email."""
    email = email.strip().lower()
    deleted = delete_sessions_by_email(email)
    return {"email": email, "sessions_deleted": deleted}


@router.get("/users/{email}/roles")
async def list_user_roles(
    email: str,
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List roles for user."""
    email = email.strip().lower()
    client = _client()
    try:
        rows = client.run(aq.LIST_USER_ROLES, email=email)
        return [{"role": r.get("role"), "org_id": r.get("org_id")} for r in rows]
    finally:
        client.close()


@router.post("/users/{email}/roles")
async def assign_user_role(
    email: str,
    body: AssignRoleBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Assign role (optionally scoped to org_id)."""
    email = email.strip().lower()
    client = _client()
    try:
        client.run(
            aq.ASSIGN_USER_ROLE,
            email=email,
            role_name=body.role_name,
            org_id=body.org_id or "",
        )
        return {"role": body.role_name, "org_id": body.org_id}
    finally:
        client.close()


@router.delete("/users/{email}/roles/{role_name}")
async def remove_user_role(
    email: str,
    role_name: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Remove role."""
    email = email.strip().lower()
    client = _client()
    try:
        client.run(aq.REMOVE_USER_ROLE, email=email, role_name=role_name)
        return {"role": role_name}
    finally:
        client.close()


# ------------------------------------------------------------------
# Session endpoints
# ------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all active sessions (email, session_id, ttl_seconds)."""
    sessions = list_all_sessions()
    return [
        {
            "session_id": s.get("session_id"),
            "email": s.get("email", ""),
            "ttl_seconds": s.get("ttl_seconds", 0),
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def delete_single_session(
    session_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Force-expire a single session."""
    delete_session(session_id)
    return {"session_id": session_id}


@router.delete("/sessions")
async def delete_all_sessions_endpoint(
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Force-expire all sessions (emergency)."""
    deleted = delete_all_sessions()
    return {"sessions_deleted": deleted}


# ------------------------------------------------------------------
# Group endpoints
# ------------------------------------------------------------------


@router.get("/groups")
async def list_groups(
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all groups."""
    client = _client()
    try:
        rows = client.run(aq.LIST_GROUPS)
        return [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "description": r.get("description"),
                "org_id": r.get("org_id"),
                "org_name": r.get("org_name"),
                "member_count": r.get("member_count", 0),
                "created_at": _neo4j_datetime_str(r.get("created_at")),
            }
            for r in rows
        ]
    finally:
        client.close()


@router.post("/groups")
async def create_group(
    body: CreateGroupBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create group (name, description, org_id)."""
    group_id = str(uuid.uuid4())
    client = _client()
    try:
        client.run(
            aq.CREATE_GROUP,
            id=group_id,
            name=body.name,
            description=body.description or "",
            org_id=body.org_id or "",
        )
        return {"id": group_id}
    finally:
        client.close()


@router.patch("/groups/{group_id}")
async def patch_group(
    group_id: str,
    body: PatchGroupBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Rename/redescribe group."""
    updates = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None
    }
    if not updates:
        return {"id": group_id}
    client = _client()
    try:
        client.run(aq.UPDATE_GROUP, id=group_id, updates=updates)
        return {"id": group_id}
    finally:
        client.close()


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Delete group."""
    client = _client()
    try:
        client.run(aq.DELETE_GROUP, id=group_id)
        return {"id": group_id}
    finally:
        client.close()


@router.get("/groups/{group_id}/members")
async def list_group_members(
    group_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List members."""
    client = _client()
    try:
        rows = client.run(aq.LIST_GROUP_MEMBERS, id=group_id)
        return [{"email": r.get("email"), "name": r.get("name")} for r in rows]
    finally:
        client.close()


@router.post("/groups/{group_id}/members")
async def add_group_member(
    group_id: str,
    body: AddGroupMemberBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Add member by email."""
    email = body.email.strip().lower()
    client = _client()
    try:
        client.run(aq.ADD_GROUP_MEMBER, group_id=group_id, email=email)
        return {"email": email}
    except Exception as e:
        raise HTTPException(400, str(e))
    finally:
        client.close()


@router.delete("/groups/{group_id}/members/{email}")
async def remove_group_member(
    group_id: str,
    email: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Remove member."""
    email = email.strip().lower()
    client = _client()
    try:
        client.run(aq.REMOVE_GROUP_MEMBER, group_id=group_id, email=email)
        return {"email": email}
    finally:
        client.close()


# ------------------------------------------------------------------
# Auth config endpoints
# ------------------------------------------------------------------


def _get_auth_config_from_db(client: PatientGraphClient) -> dict[str, Any]:
    """Read SystemConfig from Neo4j (helper, no auth)."""
    rows = client.run(aq.GET_SYSTEM_CONFIG, id="auth")
    if not rows:
        return {
            "session_ttl_hours": 168,
            "idle_timeout_minutes": 30,
            "cookie_secure": False,
            "require_mfa": False,
        }
    r = rows[0]
    return {
        "session_ttl_hours": r.get("session_ttl_hours", 168),
        "idle_timeout_minutes": r.get("idle_timeout_minutes", 30),
        "cookie_secure": r.get("cookie_secure", False),
        "require_mfa": r.get("require_mfa", False),
    }


@router.get("/auth-config")
async def get_auth_config(
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Read SystemConfig from Neo4j."""
    client = _client()
    try:
        return _get_auth_config_from_db(client)
    finally:
        client.close()


@router.patch("/auth-config")
async def patch_auth_config(
    body: PatchAuthConfigBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Update SystemConfig."""
    client = _client()
    try:
        current = _get_auth_config_from_db(client)
        updates = body.model_dump(exclude_unset=True)
        session_ttl = updates.get("session_ttl_hours", current["session_ttl_hours"])
        idle = updates.get("idle_timeout_minutes", current["idle_timeout_minutes"])
        cookie_secure = updates.get("cookie_secure", current["cookie_secure"])
        require_mfa = updates.get("require_mfa", current["require_mfa"])
        client.run(
            aq.UPSERT_SYSTEM_CONFIG,
            id="auth",
            session_ttl_hours=session_ttl,
            idle_timeout_minutes=idle,
            cookie_secure=cookie_secure,
            require_mfa=require_mfa,
        )
        return {"session_ttl_hours": session_ttl, "idle_timeout_minutes": idle}
    finally:
        client.close()


# ------------------------------------------------------------------
# Roles (read-only for UI)
# ------------------------------------------------------------------


@router.get("/roles")
async def list_roles(
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all roles."""
    client = _client()
    try:
        rows = client.run(aq.LIST_ROLES)
        return [
            {
                "name": r.get("name"),
                "permissions": r.get("permissions", []),
                "description": r.get("description"),
            }
            for r in rows
        ]
    finally:
        client.close()
