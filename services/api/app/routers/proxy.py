"""Proxy endpoints: forward requests to FHIR API, Analytics API, and Core API with Bearer token.

Frontend calls /api/proxy/fhir/*, /api/proxy/benchmarks/*, /api/proxy/analytics/*,
/api/proxy/pipeline/*, and /api/proxy/anchor-review/* with session cookie.
Backend adds Authorization header and forwards to upstream services.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
import httpx
from starlette.requests import ClientDisconnect

from app.deps import get_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])


def _service_base(base_key: str, url_key: str, default: str) -> str:
    """Resolve service base URL from *_BASE first, then *_URL, then default."""
    return (os.getenv(base_key) or os.getenv(url_key) or default).rstrip("/")


FHIR_BASE = _service_base("FHIR_API_BASE", "FHIR_API_URL", "http://localhost:8002")
ANALYTICS_BASE = _service_base(
    "ANALYTICS_API_BASE",
    "ANALYTICS_API_URL",
    "http://localhost:8003",
)
CORE_API_BASE = _service_base("CORE_API_BASE", "CORE_API_URL", "http://localhost:8000")


async def _proxy_request(
    method: str,
    path: str,
    base: str,
    token: str,
    request: Request,
) -> httpx.Response:
    """Forward request to upstream with Bearer token and session header.

    GAP-001: X-User-Email removed. X-Leo-Session forwarded so downstream
    services can resolve org scope from the shared Redis session store.
    """
    url = f"{base}{path}"
    headers = dict(request.headers)
    is_core_target = base.lower() == CORE_API_BASE.lower()
    blocked_headers = ("host", "content-length", "transfer-encoding", "connection")
    # Core API proxy calls rely on the browser session cookie for
    # get_caller_scope_from_request. Keep cookie only for same-core proxying.
    if not is_core_target:
        blocked_headers = blocked_headers + ("cookie",)
    for h in blocked_headers:
        headers.pop(h, None)
    headers["Authorization"] = f"Bearer {token}"
    session_id = request.cookies.get("leo_session", "")
    if session_id:
        headers["X-Leo-Session"] = session_id
    try:
        body = await request.body() if method in ("POST", "PUT", "PATCH") else None
    except ClientDisconnect:
        logger.info(
            "Client disconnected before request body was fully received: %s %s",
            method,
            url,
        )
        raise
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            return await client.request(method, url, headers=headers, content=body)
    except httpx.TimeoutException as exc:
        logger.warning("Proxy upstream timeout: %s %s", method, url)
        raise HTTPException(
            status_code=504,
            detail="Upstream service timed out. Please retry with a smaller result set.",
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("Proxy upstream request error: %s %s error=%s", method, url, exc)
        raise HTTPException(
            status_code=502,
            detail="Upstream service is unavailable. Please retry shortly.",
        ) from exc


def _copy_headers(resp: httpx.Response) -> dict:
    skip = {"transfer-encoding", "content-encoding", "content-length"}
    return {k: v for k, v in resp.headers.items() if k.lower() not in skip}


def _client_disconnect_response() -> Response:
    return Response(content=b"", status_code=499)


@router.api_route(
    "/benchmarks/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_benchmarks(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
):
    """Proxy to FHIR API benchmarks (BenchmarkSet, BenchmarkRule, upload, etc.)."""
    full_path = f"/benchmarks/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    try:
        resp = await _proxy_request(
            request.method, full_path, FHIR_BASE, token, request
        )
    except ClientDisconnect:
        return _client_disconnect_response()
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route(
    "/fhir/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_fhir(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
):
    """Proxy to FHIR API."""
    full_path = f"/fhir/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    try:
        resp = await _proxy_request(
            request.method, full_path, FHIR_BASE, token, request
        )
    except ClientDisconnect:
        return _client_disconnect_response()
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route(
    "/analytics/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_analytics(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
):
    """Proxy to Analytics API."""
    full_path = f"/analytics/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    try:
        resp = await _proxy_request(
            request.method, full_path, ANALYTICS_BASE, token, request
        )
    except ClientDisconnect:
        return _client_disconnect_response()
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route(
    "/pipeline/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_pipeline(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
):
    """Proxy pipeline endpoints to Core API (avoids client-side /api/proxy prefix mismatch)."""
    full_path = f"/pipeline/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    try:
        resp = await _proxy_request(
            request.method, full_path, CORE_API_BASE, token, request
        )
    except ClientDisconnect:
        return _client_disconnect_response()
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route(
    "/anchor-review/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_anchor_review(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
):
    """Proxy anchor-review endpoints to Core API (same-origin, adds Bearer from session)."""
    full_path = f"/anchor-review/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    try:
        resp = await _proxy_request(
            request.method, full_path, CORE_API_BASE, token, request
        )
    except ClientDisconnect:
        return _client_disconnect_response()
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )
