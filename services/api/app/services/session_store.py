"""Redis-backed session store for OAuth tokens.

Uses REDIS_URL or parses AZURE_REDIS_CONNECTION_STRING.
Session keys: auth:session:{session_id} with TTL.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from typing import Any

logger = logging.getLogger(__name__)

SESSION_PREFIX = "auth:session:"
SESSION_TTL = 60 * 60 * 24 * 7  # 7 days
COOKIE_NAME = "leo_session"


def _get_redis_url() -> str | None:
    """Build Redis URL from env. Returns None if not configured."""
    if os.getenv("DISABLE_REDIS") in ("true", "1"):
        return None
    url = os.getenv("REDIS_URL")
    if url:
        return url
    conn = os.getenv("AZURE_REDIS_CONNECTION_STRING")
    if not conn:
        return None
    # Parse: host:port,password=...,ssl=True
    parts = conn.split(",")
    host_port = parts[0].strip()
    password = ""
    use_ssl = False
    for p in parts[1:]:
        eq = p.find("=")
        if eq <= 0:
            continue
        k, v = p[:eq].strip().lower(), p[eq + 1 :].strip()
        if k == "password":
            password = v
        elif k == "ssl" and v.lower() in ("true", "1"):
            use_ssl = True
    scheme = "rediss" if use_ssl else "redis"
    if ":" in host_port:
        host, port = host_port.split(":", 1)
    else:
        host, port = host_port, "6379"
    if password:
        return f"{scheme}://:{password}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


_redis_client: Any = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        url = _get_redis_url()
        if not url:
            return None
        try:
            import redis
            _redis_client = redis.from_url(url, decode_responses=True)
            _redis_client.ping()
            logger.info("[Auth] Redis session store connected")
        except Exception as e:
            logger.warning("[Auth] Redis not available: %s", e)
            _redis_client = False  # Mark as attempted
    return _redis_client if _redis_client else None


def create_session_id() -> str:
    return secrets.token_urlsafe(32)


def save_session(session_id: str, data: dict[str, Any]) -> None:
    r = _get_redis()
    if not r:
        return
    key = f"{SESSION_PREFIX}{session_id}"
    r.setex(key, SESSION_TTL, json.dumps(data, default=str))


def load_session(session_id: str) -> dict[str, Any] | None:
    r = _get_redis()
    if not r:
        return None
    key = f"{SESSION_PREFIX}{session_id}"
    raw = r.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def delete_session(session_id: str) -> None:
    r = _get_redis()
    if r:
        r.delete(f"{SESSION_PREFIX}{session_id}")
