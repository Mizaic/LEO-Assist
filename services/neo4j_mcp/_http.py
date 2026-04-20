"""HTTP helper functions for API-backed MCP operations.

Atlas trace:
  DO: DO-5F438C17
  DI: DI-5700882E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F438C17")
"""

from __future__ import annotations

import os
from typing import Any

import httpx

CORE_API_BASE_URL = os.getenv("CORE_API_BASE_URL", "http://localhost:8000")
ANALYTICS_API_BASE_URL = os.getenv(
    "ANALYTICS_API_BASE_URL",
    "http://localhost:8003",
)
LEO_MCP_COOKIE = os.getenv("LEO_MCP_COOKIE", "")
DEFAULT_TIMEOUT = 30.0


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        chunk = part.strip()
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        cookies[key.strip()] = value.strip()
    return cookies


def _request(
    *,
    method: str,
    base_url: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cookies = _parse_cookie_header(LEO_MCP_COOKIE)
    url = f"{base_url.rstrip('/')}{path}"
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        response = client.request(
            method,
            url,
            params=params or {},
            json=json_body,
            cookies=cookies,
        )
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("application/json"):
        payload: Any = response.json()
        if isinstance(payload, dict):
            return payload
        return {"items": payload}
    return {"text": response.text}


def core_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET request to core API."""
    return _request(method="GET", base_url=CORE_API_BASE_URL, path=path, params=params)


def core_post(path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST request to core API."""
    return _request(
        method="POST",
        base_url=CORE_API_BASE_URL,
        path=path,
        json_body=json_body,
    )


def core_patch(path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    """PATCH request to core API."""
    return _request(
        method="PATCH",
        base_url=CORE_API_BASE_URL,
        path=path,
        json_body=json_body,
    )


def analytics_post(
    path: str,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST request to analytics API."""
    return _request(
        method="POST",
        base_url=ANALYTICS_API_BASE_URL,
        path=path,
        json_body=json_body,
    )


def analytics_patch(
    path: str,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """PATCH request to analytics API."""
    return _request(
        method="PATCH",
        base_url=ANALYTICS_API_BASE_URL,
        path=path,
        json_body=json_body,
    )

