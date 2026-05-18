"""On-behalf-of token exchange for Microsoft Graph (delegated).

Atlas trace:
  DO: DO-313A49AE
  DI: DI-31F4C232, DI-5A18A227, DI-6CF7FCE0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-313A49AE")

Given the user's session access-token (audience = LEO API), exchange it
for a Graph access-token using the Azure AD OBO flow. Graph tokens MUST
NOT be persisted to disk; this module caches them in Redis only when
Redis is configured, with a TTL strictly less than the token's ``exp``
claim. See DI-3610585D (amended) and DI-6CF7FCE0 acceptance criteria.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

import httpx

from libs.graph_client.errors import GraphClientError, InsufficientConsent

logger = logging.getLogger(__name__)

OBO_GRANT_TYPE = "urn:ietf:params:oauth:grant_type:jwt-bearer"
OBO_TOKEN_USE = "on_behalf_of"
GRAPH_RESOURCE = "https://graph.microsoft.com"

# How many seconds of headroom we leave between the cached token's actual
# `exp` and the Redis TTL. Prevents handing back a token that expires
# mid-request.
_TTL_HEADROOM_SECONDS = 60


def obo_cache_key(*, email: str, tenant_id: str, scopes: list[str]) -> str:
    """Build the Redis key for an OBO cache entry.

    The key contains only a hash of the scope list so the key length is
    bounded and the scopes themselves do not appear in any log.
    """
    email_hash = hashlib.sha256((email or "").encode("utf-8")).hexdigest()[:16]
    scopes_norm = " ".join(sorted(scopes))
    scope_hash = hashlib.sha256(scopes_norm.encode("utf-8")).hexdigest()[:16]
    return f"obo:{email_hash}:{tenant_id}:{scope_hash}"


def _redis_client() -> Any | None:
    """Best-effort handle to the same Redis the session store uses.

    Returns None when Redis is disabled or unreachable; callers MUST
    treat None as "no cache" and proceed without raising.
    """
    if os.getenv("DISABLE_REDIS") in ("true", "1"):
        return None
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url, decode_responses=True, socket_timeout=2)
    except Exception as exc:
        logger.warning("OBO redis client unavailable: %s", exc)
        return None


def _read_cache(key: str) -> str | None:
    client = _redis_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        return payload.get("access_token") or None
    except Exception as exc:
        logger.warning("OBO cache read failed: %s", exc)
        return None


def _write_cache(key: str, access_token: str, exp_epoch: int) -> None:
    client = _redis_client()
    if client is None:
        return
    ttl = exp_epoch - int(time.time()) - _TTL_HEADROOM_SECONDS
    if ttl <= 0:
        return
    try:
        payload = json.dumps(
            {"access_token": access_token, "exp": exp_epoch}
        )
        client.setex(key, ttl, payload)
    except Exception as exc:
        logger.warning("OBO cache write failed: %s", exc)


def _client_id() -> str:
    return (os.getenv("AZURE_AD_CLIENT_ID") or "").strip()


def _client_secret() -> str:
    return (os.getenv("AZURE_AD_CLIENT_SECRET") or "").strip()


def _token_endpoint(tenant_id: str) -> str:
    tid = (tenant_id or "").strip() or "common"
    return f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token"


def _is_consent_failure(status: int, body: dict[str, Any]) -> bool:
    """Detect AAD's consent-required signals in an OBO error response."""
    err = (body.get("error") or "").lower()
    suberr = (body.get("suberror") or "").lower()
    if status in (400, 401) and err in ("invalid_grant", "interaction_required"):
        return True
    if "consent" in suberr or "consent" in (body.get("error_description") or "").lower():
        return True
    return False


async def exchange_for_graph_token(
    *,
    user_token: str,
    tenant_id: str,
    scopes: list[str],
    email: str,
    http_client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> str:
    """Exchange the caller's API access-token for a Graph access-token.

    Raises:
        InsufficientConsent: AAD reported a consent failure for the
            requested scopes (caller must surface admin_consent_url).
        GraphClientError: any other failure from AAD (network, 5xx).
    """
    if not user_token:
        raise GraphClientError("OBO requires the caller's access token")
    cache_key = obo_cache_key(email=email, tenant_id=tenant_id, scopes=scopes)
    if use_cache:
        cached = _read_cache(cache_key)
        if cached:
            return cached

    cid = _client_id()
    secret = _client_secret()
    if not cid or not secret:
        raise GraphClientError("Azure AD client credentials not configured")

    data = {
        "client_id": cid,
        "client_secret": secret,
        "grant_type": OBO_GRANT_TYPE,
        "assertion": user_token,
        "scope": " ".join(scopes),
        "requested_token_use": OBO_TOKEN_USE,
    }
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=10)
    try:
        resp = await client.post(_token_endpoint(tenant_id), data=data)
    finally:
        if own_client:
            await client.aclose()

    body: dict[str, Any]
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code != 200:
        if _is_consent_failure(resp.status_code, body):
            raise InsufficientConsent(
                body.get("error_description") or "consent required",
                status_code=resp.status_code,
                graph_error_code=body.get("error") or "",
            )
        raise GraphClientError(
            body.get("error_description") or f"OBO failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            graph_error_code=body.get("error") or "",
        )

    access_token = body.get("access_token") or ""
    if not access_token:
        raise GraphClientError("OBO response missing access_token")
    expires_in = int(body.get("expires_in") or 0)
    exp_epoch = int(time.time()) + expires_in
    if use_cache and expires_in > _TTL_HEADROOM_SECONDS:
        _write_cache(cache_key, access_token, exp_epoch)
    return access_token
