"""Redis-backed session store for OAuth tokens.

Uses REDIS_URL or parses AZURE_REDIS_CONNECTION_STRING.
Session keys: auth:session:{session_id} with TTL.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

SESSION_PREFIX = "auth:session:"
SESSION_TTL = 60 * 60 * 24 * 7  # 7 days
COOKIE_NAME = "leo_session"

# Azure Redis can drop idle connections; retry up to 3 times with backoff.
_REDIS_CONNECT_TIMEOUT = 5   # seconds to establish the TCP/TLS connection
_REDIS_SOCKET_TIMEOUT = 5    # seconds for a command to complete
_REDIS_MAX_RETRIES = 3       # attempts per operation before giving up
_REDIS_HEALTH_CHECK = 30     # seconds between connection-pool health pings


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
_memory_store: dict[str, tuple[float, dict[str, Any]]] = {}
_memory_store_lock = threading.Lock()


def _purge_expired_memory_sessions(now: float | None = None) -> None:
    """Remove expired in-memory sessions."""
    ts = now if now is not None else time.time()
    expired = [sid for sid, (expires_at, _) in _memory_store.items() if expires_at <= ts]
    for sid in expired:
        _memory_store.pop(sid, None)


def _get_redis():
    global _redis_client
    if _redis_client is None:
        url = _get_redis_url()
        if not url:
            return None
        try:
            import redis
            from redis.backoff import ExponentialBackoff
            from redis.exceptions import ConnectionError as RedisConnectionError
            from redis.exceptions import TimeoutError as RedisTimeoutError
            from redis.retry import Retry

            retry = Retry(
                ExponentialBackoff(cap=2, base=0.5),
                retries=_REDIS_MAX_RETRIES,
            )
            _redis_client = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
                socket_timeout=_REDIS_SOCKET_TIMEOUT,
                retry=retry,
                retry_on_error=[RedisConnectionError, RedisTimeoutError],
                health_check_interval=_REDIS_HEALTH_CHECK,
            )
            _redis_client.ping()
            logger.info("[Auth] Redis session store connected")
        except Exception as e:
            logger.warning("[Auth] Redis not available: %s", e)
            _redis_client = False  # Mark as permanently unavailable this process lifetime
    return _redis_client if _redis_client else None


def _redis_op(fn, *args, **kwargs):
    """Execute a Redis callable; reset the client and fall back on transient errors."""
    global _redis_client
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        if isinstance(e, (RedisConnectionError, RedisTimeoutError)):
            logger.warning("[Auth] Redis transient error (%s); will reconnect on next call", e)
            _redis_client = None  # Allow reconnect next time
        else:
            logger.error("[Auth] Redis unexpected error: %s", e)
        return None


def create_session_id() -> str:
    return secrets.token_urlsafe(32)


def _memory_save(session_id: str, data: dict[str, Any]) -> None:
    with _memory_store_lock:
        _purge_expired_memory_sessions()
        _memory_store[session_id] = (time.time() + SESSION_TTL, data)


def _memory_load(session_id: str) -> dict[str, Any] | None:
    with _memory_store_lock:
        _purge_expired_memory_sessions()
        record = _memory_store.get(session_id)
    return record[1] if record else None


def _memory_delete(session_id: str) -> None:
    with _memory_store_lock:
        _memory_store.pop(session_id, None)


def save_session(session_id: str, data: dict[str, Any]) -> None:
    r = _get_redis()
    if not r:
        _memory_save(session_id, data)
        return
    key = f"{SESSION_PREFIX}{session_id}"
    result = _redis_op(r.setex, key, SESSION_TTL, json.dumps(data, default=str))
    if result is None:
        # Redis failed after retries; persist locally so the session isn't lost
        logger.warning("[Auth] Falling back to memory store for save_session")
        _memory_save(session_id, data)


def load_session(session_id: str) -> dict[str, Any] | None:
    r = _get_redis()
    if not r:
        return _memory_load(session_id)
    key = f"{SESSION_PREFIX}{session_id}"
    raw = _redis_op(r.get, key)
    if raw is None:
        # Distinguish "key missing" from "Redis error": fall back to memory
        if _redis_client is None:
            logger.warning("[Auth] Falling back to memory store for load_session")
            return _memory_load(session_id)
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def delete_session(session_id: str) -> None:
    r = _get_redis()
    if r:
        _redis_op(r.delete, f"{SESSION_PREFIX}{session_id}")
    _memory_delete(session_id)  # Always clean up memory store too
