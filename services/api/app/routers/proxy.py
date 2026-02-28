"""Proxy endpoints: forward requests to FHIR API, Analytics API, and Core API with Bearer token.

Frontend calls /api/proxy/fhir/*, /api/proxy/benchmarks/*, /api/proxy/analytics/*, and
/api/proxy/pipeline/* with session cookie.
Backend adds Authorization header and forwards to upstream services.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
import httpx

from app.deps import get_access_token, get_user_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

FHIR_BASE = os.getenv("FHIR_API_BASE", "http://localhost:8002")
ANALYTICS_BASE = os.getenv("ANALYTICS_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.getenv("CORE_API_BASE", "http://localhost:8000")


async def _proxy_request(
    method: str,
    path: str,
    base: str,
    token: str,
    user_email: str,
    request: Request,
) -> httpx.Response:
    """Forward request to upstream with Bearer token."""
    url = f"{base.rstrip('/')}{path}"
    headers = dict(request.headers)
    for h in ("host", "cookie", "content-length", "transfer-encoding", "connection"):
        headers.pop(h, None)
    headers["Authorization"] = f"Bearer {token}"
    # Org-scoped downstream APIs require caller identity for access resolution.
    headers["X-User-Email"] = user_email
    body = await request.body() if method in ("POST", "PUT", "PATCH") else None
    async with httpx.AsyncClient(timeout=60) as client:
        return await client.request(method, url, headers=headers, content=body)


def _copy_headers(resp: httpx.Response) -> dict:
    skip = {"transfer-encoding", "content-encoding", "content-length"}
    return {k: v for k, v in resp.headers.items() if k.lower() not in skip}


@router.api_route("/benchmarks/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_benchmarks(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
    user_email: Annotated[str, Depends(get_user_email)],
):
    """Proxy to FHIR API benchmarks (BenchmarkSet, BenchmarkRule, upload, etc.)."""
    full_path = f"/benchmarks/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    resp = await _proxy_request(request.method, full_path, FHIR_BASE, token, user_email, request)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route("/fhir/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_fhir(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
    user_email: Annotated[str, Depends(get_user_email)],
):
    """Proxy to FHIR API."""
    full_path = f"/fhir/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    resp = await _proxy_request(request.method, full_path, FHIR_BASE, token, user_email, request)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route("/analytics/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_analytics(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
    user_email: Annotated[str, Depends(get_user_email)],
):
    """Proxy to Analytics API."""
    full_path = f"/analytics/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    resp = await _proxy_request(request.method, full_path, ANALYTICS_BASE, token, user_email, request)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )


@router.api_route("/pipeline/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_pipeline(
    path: str,
    request: Request,
    token: Annotated[str, Depends(get_access_token)],
    user_email: Annotated[str, Depends(get_user_email)],
):
    """Proxy pipeline endpoints to Core API (avoids client-side /api/proxy prefix mismatch)."""
    full_path = f"/pipeline/{path}" if not path.startswith("/") else f"/{path}"
    if request.url.query:
        full_path = f"{full_path}?{request.url.query}"
    resp = await _proxy_request(request.method, full_path, CORE_API_BASE, token, user_email, request)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_copy_headers(resp),
        media_type=resp.headers.get("content-type"),
    )
