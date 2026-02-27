"""Redis-backed checkpoint store for durable pipeline recovery.

Each pipeline stage writes a checkpoint immediately after completing work.
On retry the stage reads the checkpoint and skips re-doing expensive work
(LLM calls, Neo4j writes that already succeeded, etc.).

Key scheme:
    classify:{patient_id}:{encounter_id}   — ClassificationResult per encounter
    analysis:{patient_id}:anchors          — AnchorResult for the patient
    analysis:{patient_id}:episodes         — EpisodeBuildResult for the patient
    analysis:{patient_id}:safety_net       — list of safety-net signal dicts
    analysis:{patient_id}:abnormal         — list of abnormal result dicts
    analysis:{patient_id}:kpis             — list of KPI metric dicts

All keys default to TTL = 86400 s (24 hours).

Connection string:
    Reads AZURE_REDIS_CONNECTION_STRING first (Azure Cache format:
    ``host:port,password=…,ssl=True,abortConnect=False``), then falls back
    to REDIS_URL (standard ``redis[s]://…`` URL).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _parse_azure_redis_url(conn_str: str) -> str:
    """Convert Azure Cache for Redis connection string to a redis[s]:// URL.

    Azure format: ``host:port,password=xxx,ssl=True,abortConnect=False``
    """
    parts = conn_str.split(",")
    host_port = parts[0].strip()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.strip()] = v.strip()

    host, port = host_port.rsplit(":", 1)
    password = params.get("password", "")
    use_ssl = params.get("ssl", "False").lower() == "true"
    scheme = "rediss" if use_ssl else "redis"

    # URL-encode the password in case it contains special characters.
    from urllib.parse import quote
    encoded_password = quote(password, safe="")
    return f"{scheme}://:{encoded_password}@{host}:{port}"


def _build_redis_url() -> str:
    azure = os.getenv("AZURE_REDIS_CONNECTION_STRING", "")
    if azure:
        return _parse_azure_redis_url(azure)
    fallback = os.getenv("REDIS_URL", "redis://localhost:6379")
    return fallback


class CheckpointStore:
    """Thread-safe Redis checkpoint store.

    Usage::

        store = CheckpointStore()

        # Write
        store.set("classify:P1:E1", {"content_type": "clinical", ...})

        # Read (returns None on miss)
        cached = store.get("classify:P1:E1")

        # Bulk delete for a patient re-run
        store.delete_pattern("classify:P1:*")
    """

    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, conn_str: str | None = None) -> None:
        import redis

        url = _parse_azure_redis_url(conn_str) if conn_str else _build_redis_url()
        self._client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> dict[str, Any] | list[Any] | None:
        """Return the stored value, or None if the key does not exist."""
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.debug("Checkpoint GET failed for key %s", key, exc_info=True)
            return None

    def set(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Serialise *value* to JSON and store it with the given TTL."""
        try:
            self._client.setex(key, ttl, json.dumps(value, default=str))
        except Exception:
            logger.debug("Checkpoint SET failed for key %s", key, exc_info=True)

    def delete(self, key: str) -> None:
        """Delete a single checkpoint key."""
        try:
            self._client.delete(key)
        except Exception:
            logger.debug("Checkpoint DELETE failed for key %s", key, exc_info=True)

    def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching *pattern* (uses SCAN to avoid blocking)."""
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    self._client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            if deleted:
                logger.info("Checkpoint: deleted %d keys matching %s", deleted, pattern)
        except Exception:
            logger.debug(
                "Checkpoint DELETE_PATTERN failed for pattern %s", pattern, exc_info=True
            )

    def incr(self, key: str, ttl: int = DEFAULT_TTL) -> int:
        """Atomically increment *key* by 1 and return the new value.

        Sets TTL on first creation.  Safe for fan-out completion counters
        because Redis INCR is atomic — exactly one caller will see each value.
        """
        try:
            value = self._client.incr(key)
            if value == 1:
                self._client.expire(key, ttl)
            return int(value)
        except Exception:
            logger.debug("Checkpoint INCR failed for key %s", key, exc_info=True)
            return -1

    def sadd(self, key: str, *values: str, ttl: int = DEFAULT_TTL) -> None:
        """Add one or more string values to the set stored at *key*."""
        try:
            self._client.sadd(key, *values)
            self._client.expire(key, ttl)
        except Exception:
            logger.debug("Checkpoint SADD failed for key %s", key, exc_info=True)

    def smembers(self, key: str) -> set[str]:
        """Return all members of the set stored at *key* (empty set on miss/error)."""
        try:
            return set(self._client.smembers(key))
        except Exception:
            logger.debug("Checkpoint SMEMBERS failed for key %s", key, exc_info=True)
            return set()

    def ping(self) -> bool:
        """Return True if the Redis connection is healthy."""
        try:
            return bool(self._client.ping())
        except Exception:
            return False
