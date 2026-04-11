"""
Inbound Bearer token validation for internal services.

Validates tokens issued by Entra ID and checks that the 'Call' app role
is present. Used as a FastAPI dependency on internal-ingress services.

Locally (no APP_ID set): validation is skipped to allow local dev without
full Entra configuration.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException, Request
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 3600


def _get_jwks(tenant_id: str) -> dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache

    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    _jwks_cache = response.json()
    _jwks_fetched_at = now
    return _jwks_cache


def validate_service_token(request: Request) -> None:
    """FastAPI dependency -- raises 401 if the token is missing or invalid."""
    app_id = os.environ.get("THIS_SERVICE_APP_ID", "")
    tenant_id = os.environ.get("AZURE_AD_TENANT_ID", "")

    if not app_id or not tenant_id:
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing service Bearer token")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        jwks = _get_jwks(tenant_id)
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=app_id,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=401, detail=f"Invalid service token: {exc}"
        ) from exc

    roles: list[str] = claims.get("roles", [])
    if "Call" not in roles:
        raise HTTPException(status_code=403, detail="Missing required app role: Call")
