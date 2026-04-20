"""Async wrapper around the Microsoft Graph endpoints used by /admin/entra/*.

Atlas trace:
  DO: DO-313A49AE
  DI: DI-31F4C232, DI-5A18A227, DI-6CF7FCE0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-313A49AE")

The wrapper is deliberately thin and explicit: every endpoint we call
is named here. There is no SDK; explicit URLs and request shapes are
easier to audit, mock, and pin in verification tests. See DI-31F4C232
for the seven endpoints exposed to the admin portal and DI-6CF7FCE0
for the audit / OBO requirements.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from libs.audit.security_log import (
    emit_entra_admin_call,
    emit_entra_admin_denied,
    emit_entra_admin_error,
)
from libs.graph_client.errors import (
    Forbidden,
    GraphClientError,
    InsufficientConsent,
    MissingUserToken,
    NotFound,
    RateLimited,
)
from libs.graph_client.obo import exchange_for_graph_token

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_DEFAULT_TIMEOUT = 15
_RATE_LIMIT_RETRY_CAP_SECONDS = 5

_CONSENT_ERROR_CODES = frozenset(
    {
        "Authorization_RequestDenied",
        "Authorization_IdentityNotFound",
        "consent_required",
        "InsufficientPrivileges",
    }
)


@dataclass(frozen=True)
class GraphScopes:
    """Canonical Graph delegated scopes the LEO app reg holds.

    Kept as a class so router and tests share a single source of truth.
    """

    DOMAIN_READ_ALL: str = "https://graph.microsoft.com/Domain.Read.All"
    USER_READ_ALL: str = "https://graph.microsoft.com/User.Read.All"
    GROUP_READ_ALL: str = "https://graph.microsoft.com/Group.Read.All"
    GROUP_READ_WRITE_ALL: str = "https://graph.microsoft.com/Group.ReadWrite.All"
    GROUP_MEMBER_READ_WRITE_ALL: str = (
        "https://graph.microsoft.com/GroupMember.ReadWrite.All"
    )

    @classmethod
    def all_required(cls) -> list[str]:
        return [
            cls.DOMAIN_READ_ALL,
            cls.USER_READ_ALL,
            cls.GROUP_READ_ALL,
            cls.GROUP_READ_WRITE_ALL,
            cls.GROUP_MEMBER_READ_WRITE_ALL,
        ]


@dataclass
class CallContext:
    """Per-request context the client needs for OBO + audit.

    `user_token` is the caller's API access-token (read from the Redis
    session, never sent to the client). `tenant_id` is the customer's
    Entra tenant id (`tid` claim) that the call is targeting.
    """

    user_token: str
    tenant_id: str
    email: str
    ip: str = ""
    extra_scopes: list[str] = field(default_factory=list)


def _admin_consent_url(tenant_id: str, scopes: list[str]) -> str:
    cid = (os.getenv("AZURE_AD_CLIENT_ID") or "").strip()
    redirect = (os.getenv("AUTH_REDIRECT_URI") or "").strip()
    scope_param = "%20".join(scopes)
    return (
        f"https://login.microsoftonline.com/{tenant_id}/v2.0/adminconsent"
        f"?client_id={cid}&redirect_uri={redirect}&scope={scope_param}"
    )


class GraphClient:
    """Thin async wrapper. One instance per /admin/entra/* call."""

    def __init__(
        self,
        ctx: CallContext,
        *,
        http_client: httpx.AsyncClient | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        if not ctx.user_token:
            raise MissingUserToken("GraphClient requires a delegated user token")
        self._ctx = ctx
        self._scopes = list(scopes or GraphScopes.all_required())
        self._http = http_client
        self._owns_http = http_client is None
        self._token: str | None = None

    async def __aenter__(self) -> "GraphClient":
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()

    async def _ensure_token(self, scopes: list[str]) -> str:
        if self._token:
            return self._token
        token = await exchange_for_graph_token(
            user_token=self._ctx.user_token,
            tenant_id=self._ctx.tenant_id,
            scopes=scopes,
            email=self._ctx.email,
            http_client=self._http,
        )
        self._token = token
        return token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        scopes: list[str],
        params: dict | None = None,
        json_body: dict | None = None,
        extra_headers: dict | None = None,
    ) -> httpx.Response:
        token = await self._ensure_token(scopes)
        headers = {"Authorization": f"Bearer {token}"}
        if extra_headers:
            headers.update(extra_headers)
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"
        assert self._http is not None  # for type-checker
        resp = await self._http.request(
            method, url, params=params, json=json_body, headers=headers
        )
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", "1"))
            await asyncio.sleep(min(retry, _RATE_LIMIT_RETRY_CAP_SECONDS))
            resp = await self._http.request(
                method, url, params=params, json=json_body, headers=headers
            )
        return resp

    async def call(
        self,
        method: str,
        path: str,
        *,
        scopes: list[str] | None = None,
        params: dict | None = None,
        json_body: dict | None = None,
        extra_headers: dict | None = None,
        summary_for_audit: str = "",
    ) -> dict[str, Any]:
        """Make a Graph call; emit one audit event; raise typed errors."""
        scope_list = list(scopes or self._scopes)
        try:
            resp = await self._request(
                method,
                path,
                scopes=scope_list,
                params=params,
                json_body=json_body,
                extra_headers=extra_headers,
            )
        except InsufficientConsent as exc:
            self._audit_denied(method, path, scope_list, str(exc))
            raise
        except GraphClientError as exc:
            self._audit_error(method, path, exc.status_code or 0, str(exc))
            raise

        if 200 <= resp.status_code < 300:
            self._audit_call(method, path, resp.status_code, scope_list, summary_for_audit)
            return _parse_body(resp)
        return self._handle_error_response(method, path, resp, scope_list)

    def _handle_error_response(
        self,
        method: str,
        path: str,
        resp: httpx.Response,
        scopes: list[str],
    ) -> dict[str, Any]:
        body = _safe_json(resp)
        err_code, err_message = _extract_graph_error(body)
        if resp.status_code == 429:
            self._audit_error(method, path, 429, "rate_limited")
            raise RateLimited(err_message or "rate limited", retry_after_seconds=0)
        if resp.status_code == 404:
            self._audit_error(method, path, 404, err_message or "not found")
            raise NotFound(err_message or "not found", status_code=404)
        if resp.status_code in (401, 403) and err_code in _CONSENT_ERROR_CODES:
            self._audit_denied(method, path, scopes, err_message or err_code)
            raise InsufficientConsent(
                err_message or "insufficient consent",
                status_code=resp.status_code,
                graph_error_code=err_code,
            )
        if resp.status_code == 403:
            self._audit_error(method, path, 403, err_message or "forbidden")
            raise Forbidden(
                err_message or "forbidden",
                status_code=403,
                graph_error_code=err_code,
            )
        self._audit_error(method, path, resp.status_code, err_message or "graph_error")
        raise GraphClientError(
            err_message or f"Graph error: HTTP {resp.status_code}",
            status_code=resp.status_code,
            graph_error_code=err_code,
        )

    def _audit_call(
        self,
        method: str,
        path: str,
        status: int,
        scopes: list[str],
        summary: str,
    ) -> None:
        emit_entra_admin_call(
            email=self._ctx.email,
            ip=self._ctx.ip,
            tenant_id=self._ctx.tenant_id,
            graph_endpoint=path,
            http_method=method,
            status_code=status,
            scopes=scopes,
            summary=summary,
        )

    def _audit_denied(
        self,
        method: str,
        path: str,
        scopes: list[str],
        reason: str,
    ) -> None:
        emit_entra_admin_denied(
            email=self._ctx.email,
            ip=self._ctx.ip,
            tenant_id=self._ctx.tenant_id,
            graph_endpoint=path,
            http_method=method,
            scopes=scopes,
            reason=reason,
        )

    def _audit_error(
        self,
        method: str,
        path: str,
        status: int,
        detail: str,
    ) -> None:
        emit_entra_admin_error(
            email=self._ctx.email,
            ip=self._ctx.ip,
            tenant_id=self._ctx.tenant_id,
            graph_endpoint=path,
            http_method=method,
            status_code=status,
            error_code="",
            detail=detail,
        )

    # ---- High-level Graph operations ----

    async def list_domains(self) -> list[dict[str, Any]]:
        body = await self.call(
            "GET",
            "/domains",
            scopes=[GraphScopes.DOMAIN_READ_ALL],
            summary_for_audit="list_domains",
        )
        return list(body.get("value") or [])

    async def search_users(
        self, query: str, *, top: int = 25
    ) -> list[dict[str, Any]]:
        q = (query or "").strip().replace('"', '')
        if not q:
            return []
        search = f'"displayName:{q}" OR "mail:{q}"'
        body = await self.call(
            "GET",
            "/users",
            scopes=[GraphScopes.USER_READ_ALL],
            params={
                "$search": search,
                "$top": str(min(top, 100)),
                "$select": "id,displayName,mail,userPrincipalName",
            },
            extra_headers={"ConsistencyLevel": "eventual"},
            summary_for_audit=f"search_users q={q[:32]}",
        )
        return list(body.get("value") or [])

    async def list_groups(
        self, *, prefix: str | None = None, top: int = 50
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "$top": str(min(top, 200)),
            "$select": "id,displayName,description,securityEnabled,mailEnabled",
        }
        if prefix:
            safe = prefix.replace("'", "''")
            params["$filter"] = f"startswith(displayName,'{safe}')"
        body = await self.call(
            "GET",
            "/groups",
            scopes=[GraphScopes.GROUP_READ_ALL],
            params=params,
            summary_for_audit=f"list_groups prefix={prefix or ''}",
        )
        return list(body.get("value") or [])

    async def create_security_group(
        self,
        *,
        display_name: str,
        description: str = "",
        mail_nickname: str | None = None,
    ) -> dict[str, Any]:
        nickname = (mail_nickname or _slugify(display_name))[:64]
        payload = {
            "displayName": display_name,
            "description": description,
            "mailEnabled": False,
            "securityEnabled": True,
            "mailNickname": nickname,
        }
        body = await self.call(
            "POST",
            "/groups",
            scopes=[GraphScopes.GROUP_READ_WRITE_ALL],
            json_body=payload,
            summary_for_audit=f"create_security_group {display_name}",
        )
        return body

    async def add_group_member(
        self, *, group_object_id: str, user_object_id: str
    ) -> None:
        ref = f"{GRAPH_BASE}/directoryObjects/{user_object_id}"
        await self.call(
            "POST",
            f"/groups/{group_object_id}/members/$ref",
            scopes=[GraphScopes.GROUP_MEMBER_READ_WRITE_ALL],
            json_body={"@odata.id": ref},
            summary_for_audit=(
                f"add_member group={group_object_id} user={user_object_id}"
            ),
        )

    async def remove_group_member(
        self, *, group_object_id: str, user_object_id: str
    ) -> None:
        await self.call(
            "DELETE",
            f"/groups/{group_object_id}/members/{user_object_id}/$ref",
            scopes=[GraphScopes.GROUP_MEMBER_READ_WRITE_ALL],
            summary_for_audit=(
                f"remove_member group={group_object_id} user={user_object_id}"
            ),
        )


def _parse_body(resp: httpx.Response) -> dict[str, Any]:
    if not resp.content:
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        return resp.json() or {}
    except Exception:
        return {}


def _extract_graph_error(body: dict[str, Any]) -> tuple[str, str]:
    err = body.get("error") or {}
    if isinstance(err, dict):
        return (str(err.get("code") or ""), str(err.get("message") or ""))
    if isinstance(err, str):
        return (err, str(body.get("error_description") or ""))
    return ("", "")


def _slugify(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")


async def probe_capability(
    ctx: CallContext,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Best-effort capability probe for the caller's tenant.

    Calls the cheapest read-only endpoint per scope and reports which
    succeeded. The router caches the result per-tenant in Redis with a
    60s TTL (acceptance criterion in DI-31F4C232).
    """
    capability = {
        "can_list_domains": False,
        "can_search_users": False,
        "can_list_groups": False,
        "can_write_groups": False,
        "can_manage_membership": False,
        "scopes_granted": [],
        "scopes_required": GraphScopes.all_required(),
        "admin_consent_url": _admin_consent_url(
            ctx.tenant_id, GraphScopes.all_required()
        ),
    }
    granted: list[str] = []
    async with GraphClient(ctx, http_client=http_client) as gc:
        capability["can_list_domains"] = await _try_probe(
            gc.list_domains, GraphScopes.DOMAIN_READ_ALL, granted
        )
        capability["can_search_users"] = await _try_probe(
            lambda: gc.search_users("a", top=1),
            GraphScopes.USER_READ_ALL,
            granted,
        )
        capability["can_list_groups"] = await _try_probe(
            lambda: gc.list_groups(top=1),
            GraphScopes.GROUP_READ_ALL,
            granted,
        )
    # Write capabilities are inferred from the consented scope set, not
    # exercised here -- creating / deleting a group as a probe would
    # leave artefacts in the tenant.
    if GraphScopes.GROUP_READ_WRITE_ALL in granted or capability["can_list_groups"]:
        capability["can_write_groups"] = (
            GraphScopes.GROUP_READ_WRITE_ALL in granted
        )
    capability["can_manage_membership"] = (
        GraphScopes.GROUP_MEMBER_READ_WRITE_ALL in granted
    )
    capability["scopes_granted"] = granted
    return capability


async def _try_probe(coro_factory, scope: str, granted: list[str]) -> bool:
    try:
        await coro_factory()
    except InsufficientConsent:
        return False
    except (Forbidden, NotFound, RateLimited, GraphClientError):
        return False
    granted.append(scope)
    return True
