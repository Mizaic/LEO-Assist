"""Shared session lookup for inter-service auth.

Any service that receives X-Leo-Session can verify it by reading from Redis.
Requires REDIS_URL env var (set from Key Vault in production, .env locally).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SESSION_PREFIX = "auth:session:"
_CONNECT_TIMEOUT = 5
_SOCKET_TIMEOUT = 5

_client: Any = None


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
        raw = r.get(f"{SESSION_PREFIX}{session_id}")
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Session load error: %s", exc)
        return None
