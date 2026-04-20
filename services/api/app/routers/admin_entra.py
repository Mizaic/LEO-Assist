"""Admin portal Microsoft Graph endpoints (`/admin/entra/*`).

All endpoints are platform-admin gated and run on-behalf-of the signed-in
admin -- LEO never holds application-only Graph permissions. See:

- DI-31F4C232 -- functional requirements (capability probe + 7 endpoints).
- DI-5A18A227 -- manual fallback when Graph is unavailable.
- DI-6CF7FCE0 -- security/audit (delegated, audited, no PII in cache).
- DI-3610585D (amended) -- runtime callback stays Graph-free.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps import get_session_data, require_admin
from app.services.session_store import _get_redis  # type: ignore[attr-defined]
from libs.auth.org_scope import CallerScope
from libs.cypher import admin_queries as aq
from libs.graph_client import (
    Forbidden,
    GraphClient,
    GraphClientError,
    GraphScopes,
    InsufficientConsent,
    MissingUserToken,
    NotFound,
    RateLimited,
    probe_capability,
)
from libs.graph_client.client import CallContext
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/entra", tags=["admin-entra"])

_CAPABILITY_TTL_SECONDS = 60
_CAPABILITY_PREFIX = "entra:capability:"


# ------------------------------------------------------------------
# Request/response models
# ------------------------------------------------------------------


class CreateEntraGroupBody(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    mail_nickname: Optional[str] = None
    org_id: Optional[str] = None
    bind_role_name: Optional[str] = None


class BindEntraGroupBody(BaseModel):
    display_name: str
    name: str
    role_name: str
    description: str = ""
    org_id: Optional[str] = None
    confirm_display_name: str = Field(
        ...,
        description=(
            "Caller MUST type the group's exact displayName to confirm. "
            "Prevents a misclick from binding the wrong group."
        ),
    )


class AddGroupMemberBody(BaseModel):
    user_object_id: str = Field(..., min_length=1)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_call_context(
    request: Request,
    session_data: dict,
) -> CallContext:
    token = session_data.get("access_token") or ""
    email = (session_data.get("email") or "").strip().lower()
    tid = (session_data.get("entra_tenant_id") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="No access token")
    if not tid:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "tenant_unknown",
                "message": (
                    "The signed-in admin's tenant id was not captured on "
                    "login. Sign out and back in to refresh the session."
                ),
            },
        )
    ip = ""
    if request.client is not None:
        ip = request.client.host or ""
    return CallContext(
        user_token=token,
        tenant_id=tid,
        email=email,
        ip=ip,
    )


def _capability_cache_key(tenant_id: str, email: str) -> str:
    return f"{_CAPABILITY_PREFIX}{tenant_id}:{email}"


def _read_capability_cache(key: str) -> Optional[dict[str, Any]]:
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Capability cache read failed: %s", exc)
        return None


def _write_capability_cache(key: str, payload: dict[str, Any]) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(key, _CAPABILITY_TTL_SECONDS, json.dumps(payload, default=str))
    except Exception as exc:
        logger.warning("Capability cache write failed: %s", exc)


def _graph_error_to_http(exc: GraphClientError) -> HTTPException:
    """Map typed Graph errors to stable, UI-friendly HTTP responses."""
    if isinstance(exc, InsufficientConsent):
        return HTTPException(
            status_code=403,
            detail={
                "code": "consent_required",
                "message": str(exc),
                "graph_error_code": exc.graph_error_code,
            },
        )
    if isinstance(exc, MissingUserToken):
        return HTTPException(status_code=401, detail="No access token")
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RateLimited):
        return HTTPException(status_code=429, detail="Microsoft Graph rate limit hit")
    if isinstance(exc, Forbidden):
        return HTTPException(
            status_code=403,
            detail={
                "code": "forbidden",
                "message": str(exc),
                "graph_error_code": exc.graph_error_code,
            },
        )
    return HTTPException(
        status_code=502,
        detail={
            "code": "graph_error",
            "message": str(exc),
            "graph_error_code": exc.graph_error_code,
        },
    )


def _graph_client() -> GraphClient:  # pragma: no cover - patched in tests
    raise NotImplementedError


def _make_graph_client(ctx: CallContext) -> GraphClient:
    """Indirection so tests can patch the constructor without monkeypatching httpx."""
    return GraphClient(ctx)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/capability")
async def get_capability(
    request: Request,
    session_data: dict = Depends(get_session_data),
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Probe the caller's tenant for the LEO Graph permission set.

    Cached in Redis for 60 seconds keyed by (tenant, admin email) so the
    UI's "Entra integration" tab can render without a Graph round-trip
    on every navigation.
    """
    ctx = _build_call_context(request, session_data)
    key = _capability_cache_key(ctx.tenant_id, ctx.email)
    cached = _read_capability_cache(key)
    if cached:
        cached["from_cache"] = True
        return cached
    try:
        capability = await probe_capability(ctx)
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)
    capability["tenant_id"] = ctx.tenant_id
    capability["from_cache"] = False
    capability["probed_at"] = int(time.time())
    _write_capability_cache(key, capability)
    return capability


@router.get("/domains")
async def list_domains(
    request: Request,
    session_data: dict = Depends(get_session_data),
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    ctx = _build_call_context(request, session_data)
    try:
        async with _make_graph_client(ctx) as gc:
            domains = await gc.list_domains()
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)
    return {"tenant_id": ctx.tenant_id, "domains": domains}


@router.get("/users")
async def search_users(
    request: Request,
    q: str = "",
    top: int = 25,
    session_data: dict = Depends(get_session_data),
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    if not q.strip():
        return {"tenant_id": "", "users": []}
    ctx = _build_call_context(request, session_data)
    try:
        async with _make_graph_client(ctx) as gc:
            users = await gc.search_users(q, top=top)
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)
    return {"tenant_id": ctx.tenant_id, "users": users}


@router.get("/groups")
async def list_groups(
    request: Request,
    prefix: str = "",
    top: int = 50,
    session_data: dict = Depends(get_session_data),
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    ctx = _build_call_context(request, session_data)
    try:
        async with _make_graph_client(ctx) as gc:
            groups = await gc.list_groups(prefix=prefix or None, top=top)
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)
    return {"tenant_id": ctx.tenant_id, "groups": groups}


@router.post("/groups")
async def create_group(
    body: CreateEntraGroupBody,
    request: Request,
    session_data: dict = Depends(get_session_data),
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new Entra security group AND mirror it as a shadow node.

    Optionally bind the new shadow group to a LEO role in the same call;
    the bind step is best-effort -- failure does not roll back the Graph
    create (the admin can retry the bind via /groups/{oid}/bind).
    """
    ctx = _build_call_context(request, session_data)
    try:
        async with _make_graph_client(ctx) as gc:
            created = await gc.create_security_group(
                display_name=body.display_name,
                description=body.description,
                mail_nickname=body.mail_nickname,
            )
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)

    object_id = str(created.get("id") or "")
    if not object_id:
        raise HTTPException(502, "Graph create_group returned no id")
    shadow = _upsert_shadow(
        entra_object_id=object_id,
        name=created.get("displayName") or body.display_name,
        description=body.description,
        entra_tenant_id=ctx.tenant_id,
        org_id=body.org_id,
    )
    bind_result: dict[str, Any] | None = None
    if body.bind_role_name:
        bind_result = _bind_role(
            entra_object_id=object_id,
            role_name=body.bind_role_name,
            org_id=body.org_id,
        )
    return {
        "graph": created,
        "shadow": shadow,
        "bind": bind_result,
    }


@router.post("/groups/{group_object_id}/bind")
async def bind_group_to_role(
    group_object_id: str,
    body: BindEntraGroupBody,
    request: Request,
    session_data: dict = Depends(get_session_data),
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Bind an existing Entra security group to a LEO role.

    The caller MUST type the group's exact displayName into
    `confirm_display_name` (UI presents a 'type the name' confirm gate).
    Mismatches are rejected before any Neo4j or Graph write.
    """
    if body.confirm_display_name.strip() != body.display_name.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "confirm_mismatch",
                "message": "Confirmation did not match the group display name",
            },
        )
    ctx = _build_call_context(request, session_data)
    # Verify the group still exists in the tenant before persisting the bind.
    try:
        async with _make_graph_client(ctx) as gc:
            verified = await gc.call(
                "GET",
                f"/groups/{group_object_id}",
                scopes=[GraphScopes.GROUP_READ_ALL],
                params={"$select": "id,displayName,description"},
                summary_for_audit=f"verify_group {group_object_id}",
            )
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)

    shadow = _upsert_shadow(
        entra_object_id=str(verified.get("id") or group_object_id),
        name=str(verified.get("displayName") or body.name),
        description=body.description or str(verified.get("description") or ""),
        entra_tenant_id=ctx.tenant_id,
        org_id=body.org_id,
    )
    bind = _bind_role(
        entra_object_id=group_object_id,
        role_name=body.role_name,
        org_id=body.org_id,
    )
    return {"shadow": shadow, "bind": bind}


@router.post("/groups/{group_object_id}/members")
async def add_member(
    group_object_id: str,
    body: AddGroupMemberBody,
    request: Request,
    session_data: dict = Depends(get_session_data),
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    ctx = _build_call_context(request, session_data)
    try:
        async with _make_graph_client(ctx) as gc:
            await gc.add_group_member(
                group_object_id=group_object_id,
                user_object_id=body.user_object_id,
            )
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)
    return {
        "group_object_id": group_object_id,
        "user_object_id": body.user_object_id,
        "action": "added",
    }


@router.delete("/groups/{group_object_id}/members/{user_object_id}")
async def remove_member(
    group_object_id: str,
    user_object_id: str,
    request: Request,
    session_data: dict = Depends(get_session_data),
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    ctx = _build_call_context(request, session_data)
    try:
        async with _make_graph_client(ctx) as gc:
            await gc.remove_group_member(
                group_object_id=group_object_id,
                user_object_id=user_object_id,
            )
    except GraphClientError as exc:
        raise _graph_error_to_http(exc)
    return {
        "group_object_id": group_object_id,
        "user_object_id": user_object_id,
        "action": "removed",
    }


# ------------------------------------------------------------------
# Neo4j helpers (shadow group + role binding)
# ------------------------------------------------------------------


def _upsert_shadow(
    *,
    entra_object_id: str,
    name: str,
    description: str,
    entra_tenant_id: str,
    org_id: str | None,
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        rows = client.run(
            aq.UPSERT_ENTRA_SHADOW_GROUP,
            entra_object_id=entra_object_id,
            name=name,
            description=description or "",
            entra_tenant_id=entra_tenant_id,
            org_id=org_id or "",
        )
        if not rows:
            raise HTTPException(500, "Failed to upsert shadow group")
        row = rows[0]
        return {
            "entra_object_id": row.get("entra_object_id"),
            "id": row.get("id"),
            "name": row.get("name"),
            "description": row.get("description"),
            "entra_tenant_id": row.get("entra_tenant_id"),
            "source": row.get("source"),
        }
    finally:
        client.close()


def _bind_role(
    *,
    entra_object_id: str,
    role_name: str,
    org_id: str | None,
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        rows = client.run(
            aq.BIND_ENTRA_GROUP_TO_ROLE,
            entra_object_id=entra_object_id,
            role_name=role_name,
            org_id=org_id or "",
        )
        if not rows:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "role_not_found",
                    "message": f"Role '{role_name}' is not seeded in Neo4j",
                },
            )
        row = rows[0]
        return {
            "entra_object_id": row.get("entra_object_id"),
            "role_name": row.get("role_name"),
            "org_id": row.get("org_id"),
        }
    finally:
        client.close()
