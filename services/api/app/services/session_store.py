"""Redis-backed session store for OAuth tokens.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")

Uses REDIS_URL (standard redis[s]:// URL, written by deploy.ps1 from Azure Managed Redis).
Session keys: auth:session:{session_id} with configurable TTL.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

logger = logging.getLogger(__name__)

LEGACY_SESSION_PREFIX = "auth:session:"


def _normalise_namespace(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", (raw or "").strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "default"


def _detect_session_namespace() -> str:
    """Return a stable namespace for Redis session keys.

    Priority:
    1) SESSION_KEY_NAMESPACE (explicit override)
    2) ENVIRONMENT / APP_ENV / LEO_ENV
    3) FRONTEND_URL / AUTH_REDIRECT_URI host-derived fallback
    4) "local" (safe default for developer startup)
    """
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
# TTL configurable so the ops team can tune without a code change.
# Default 8 hours is appropriate for clinical roles (F9 -- SEC-REVIEW-2026-06-04).
_SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "8"))
SESSION_TTL = _SESSION_TTL_HOURS * 3600
COOKIE_NAME = "leo_session"

_REDIS_CONNECT_TIMEOUT = 5
_REDIS_SOCKET_TIMEOUT = 5
_REDIS_MAX_RETRIES = 3
_REDIS_HEALTH_CHECK = 30

_redis_client: Any = None


def _session_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def _legacy_session_key(session_id: str) -> str:
    return f"{LEGACY_SESSION_PREFIX}{session_id}"


def _session_prefixes() -> tuple[str, ...]:
    if SESSION_PREFIX == LEGACY_SESSION_PREFIX:
        return (SESSION_PREFIX,)
    return (SESSION_PREFIX, LEGACY_SESSION_PREFIX)


def _get_redis_url() -> str | None:
    if os.getenv("DISABLE_REDIS") in ("true", "1"):
        return None
    return os.getenv("REDIS_URL") or None


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
        except Exception as exc:
            logger.error("[Auth] Redis connection failed: %s", exc)
            _redis_client = None
    return _redis_client


def _redis_op(fn, *args, **kwargs):
    global _redis_client
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        if isinstance(exc, (RedisConnectionError, RedisTimeoutError)):
            logger.warning(
                "[Auth] Redis transient error (%s); will reconnect on next call", exc
            )
            _redis_client = None
        else:
            logger.error("[Auth] Redis unexpected error: %s", exc)
        return None


def create_session_id() -> str:
    return secrets.token_urlsafe(32)


def _require_redis():
    """Return the Redis client, or raise 503 if unavailable (GAP-011)."""
    r = _get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Session store unavailable")
    return r


def save_session(
    session_id: str, data: dict[str, Any], ttl_seconds: int = SESSION_TTL
) -> None:
    r = _require_redis()
    key = _session_key(session_id)
    result = _redis_op(r.setex, key, ttl_seconds, json.dumps(data, default=str))
    if result is None:
        raise HTTPException(status_code=503, detail="Session store unavailable")


def load_session(session_id: str) -> dict[str, Any] | None:
    r = _require_redis()
    key = _session_key(session_id)
    raw = _redis_op(r.get, key)
    # Backward compatibility: read legacy keys during rollout.
    if raw is None and SESSION_PREFIX != LEGACY_SESSION_PREFIX:
        raw = _redis_op(r.get, _legacy_session_key(session_id))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def delete_session(session_id: str) -> None:
    r = _get_redis()
    if r:
        _redis_op(r.delete, _session_key(session_id))
        if SESSION_PREFIX != LEGACY_SESSION_PREFIX:
            _redis_op(r.delete, _legacy_session_key(session_id))


def touch_session(session_id: str, idle_timeout_minutes: int = 30) -> bool:
    """Enforce idle timeout and refresh the last-activity timestamp.

    Loads the session, checks whether it has been idle longer than
    *idle_timeout_minutes*, deletes it if so (returning False), otherwise
    updates ``last_activity`` and re-saves with the original TTL (returning
    True).

    Returns False if the session does not exist or has exceeded the idle limit.
    """
    data = load_session(session_id)
    if not data:
        return False
    last_activity = data.get("last_activity")
    now = time.time()
    if last_activity is not None:
        idle_seconds = now - float(last_activity)
        if idle_seconds > idle_timeout_minutes * 60:
            delete_session(session_id)
            return False
    data["last_activity"] = now
    save_session(session_id, data, ttl_seconds=SESSION_TTL)
    return True


def list_all_sessions() -> list[dict[str, Any]]:
    """List all active sessions. Returns list of {session_id, email, ttl_seconds}.

    Requires Redis. Returns [] if Redis unavailable.
    """
    r = _get_redis()
    if not r:
        return []
    result = []
    try:
        for prefix in _session_prefixes():
            for key in r.scan_iter(match=f"{prefix}*", count=100):
                session_id = key[len(prefix) :]
                raw = _redis_op(r.get, key)
                ttl = _redis_op(r.ttl, key) or 0
                email = None
                if raw:
                    try:
                        data = json.loads(raw)
                        email = (data.get("email") or "").strip().lower()
                    except json.JSONDecodeError:
                        pass
                result.append(
                    {"session_id": session_id, "email": email or "", "ttl_seconds": ttl}
                )
    except Exception as exc:
        logger.warning("[Auth] list_all_sessions failed: %s", exc)
    return result


def delete_sessions_by_email(email: str) -> int:
    """Delete all sessions for the given email. Returns count deleted."""
    email = (email or "").strip().lower()
    if not email:
        return 0
    r = _get_redis()
    if not r:
        return 0
    deleted = 0
    try:
        for prefix in _session_prefixes():
            for key in r.scan_iter(match=f"{prefix}*", count=100):
                raw = _redis_op(r.get, key)
                if raw:
                    try:
                        data = json.loads(raw)
                        if (data.get("email") or "").strip().lower() == email:
                            _redis_op(r.delete, key)
                            deleted += 1
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        logger.warning("[Auth] delete_sessions_by_email failed: %s", exc)
    return deleted


def delete_all_sessions() -> int:
    """Delete all sessions. Returns count deleted."""
    r = _get_redis()
    if not r:
        return 0
    deleted = 0
    try:
        for prefix in _session_prefixes():
            for key in r.scan_iter(match=f"{prefix}*", count=100):
                _redis_op(r.delete, key)
                deleted += 1
    except Exception as exc:
        logger.warning("[Auth] delete_all_sessions failed: %s", exc)
    return deleted
