"""Shared session lookup for inter-service auth.

Any service that receives X-Leo-Session can verify it by reading from Redis.
Requires REDIS_URL env var (set from Key Vault in production, .env locally).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

LEGACY_SESSION_PREFIX = "auth:session:"
_CONNECT_TIMEOUT = 5
_SOCKET_TIMEOUT = 5

_client: Any = None


def _normalise_namespace(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", (raw or "").strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "default"


def _detect_session_namespace() -> str:
    explicit = (os.getenv("SESSION_KEY_NAMESPACE") or "").strip()
    if explicit:
        return _normalise_namespace(explicit)

    for env_name in ("ENVIRONMENT", "APP_ENV", "LEO_ENV"):
        value = (os.getenv(env_name) or "").strip()
        if value:
            return _normalise_namespace(value)

    for url_var in ("FRONTEND_URL", "AUTH_REDIRECT_URI"):
        candidate = (os.getenv(url_var) or "").strip()
        if not candidate:
            continue
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        host = (urlparse(candidate).hostname or "").lower().strip()
        if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
            return "local"
        if host:
            return _normalise_namespace(host.split(".")[0])
    return "local"


SESSION_NAMESPACE = _detect_session_namespace()
SESSION_PREFIX = f"auth:{SESSION_NAMESPACE}:session:"


def _session_keys(session_id: str) -> tuple[str, ...]:
    namespaced = f"{SESSION_PREFIX}{session_id}"
    if SESSION_PREFIX == LEGACY_SESSION_PREFIX:
        return (namespaced,)
    legacy = f"{LEGACY_SESSION_PREFIX}{session_id}"
    return (namespaced, legacy)


def _get_client():
    global _client
    if _client is not None:
        return _client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        _client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=_CONNECT_TIMEOUT,
            socket_timeout=_SOCKET_TIMEOUT,
        )
        _client.ping()
    except Exception as exc:
        logger.warning("Session Redis unavailable: %s", exc)
        _client = None
    return _client


def load_session(session_id: str) -> dict[str, Any] | None:
    """Return session data dict, or None if not found / Redis unavailable."""
    r = _get_client()
    if r is None:
        return None
    try:
        for key in _session_keys(session_id):
            raw = r.get(key)
            if not raw:
                continue
            return json.loads(raw)
        return None
    except Exception as exc:
        logger.warning("Session load error: %s", exc)
        return None
