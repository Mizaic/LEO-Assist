"""Redis-backed checkpoint store for durable pipeline recovery.

Each pipeline stage writes a checkpoint immediately after completing work.
On retry the stage reads the checkpoint and skips re-doing expensive work
(LLM calls, Neo4j writes that already succeeded, etc.).

Key scheme:
    classify:{patient_id}:{encounter_id}   -- ClassificationResult per encounter
    analysis:{patient_id}:anchors          -- AnchorResult for the patient
    analysis:{patient_id}:episodes         -- EpisodeBuildResult for the patient
    analysis:{patient_id}:safety_net       -- list of safety-net signal dicts
    analysis:{patient_id}:abnormal         -- list of abnormal result dicts
    analysis:{patient_id}:kpis             -- list of KPI metric dicts

All keys default to TTL = 86400 s (24 hours).

Connection:
    Reads REDIS_URL (standard ``redis[s]://...`` URL).
    Azure Managed Redis provides a ``rediss://`` URL written into Key Vault by deploy.ps1.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _build_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


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

    def __init__(self, url: str | None = None) -> None:
        import redis

        url = url or _build_redis_url()
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
                "Checkpoint DELETE_PATTERN failed for pattern %s",
                pattern,
                exc_info=True,
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
