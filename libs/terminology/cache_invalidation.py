"""Terminology cache invalidation helpers.

Atlas trace:
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9
  VT: VT-DDEB829F

SurfaceForm changes alter the resolver's source of truth. Any cached
resolution result may therefore be stale after a mapping is added, approved,
deleted, deduplicated, or deactivated.

Resolver keys are versioned (currently term_resolve:v4:...). Invalidation
matches the whole family so a version bump cannot leave stale hits.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_REDIS_URL = "redis://localhost:6379"
_DEFAULT_CLIENT_CACHE_PREFIX = "terminology:api:v4:"
# Shared with TerminologyCache.generate_key. Do not pin a version suffix.
RESOLVER_CACHE_KEY_FAMILY = "term_resolve"
RESOLVER_CACHE_INVALIDATION_PATTERN = f"{RESOLVER_CACHE_KEY_FAMILY}:*"
_CLIENT_RESOLVE_CACHE_PATTERN = "terminology:api:*:resolve:*"
_DELETE_BATCH_SIZE = 500


def _cache_patterns() -> tuple[str, ...]:
    client_prefix = os.getenv(
        "TERMINOLOGY_CACHE_PREFIX",
        _DEFAULT_CLIENT_CACHE_PREFIX,
    )
    patterns = {
        RESOLVER_CACHE_INVALIDATION_PATTERN,
        _CLIENT_RESOLVE_CACHE_PATTERN,
        f"{client_prefix}resolve:*",
    }
    return tuple(sorted(patterns))


def _delete_pattern(client: Any, pattern: str) -> int:
    deleted = 0
    batch: list[str] = []
    for key in client.scan_iter(match=pattern, count=_DELETE_BATCH_SIZE):
        batch.append(str(key))
        if len(batch) >= _DELETE_BATCH_SIZE:
            deleted += int(client.delete(*batch))
            batch.clear()
    if batch:
        deleted += int(client.delete(*batch))
    return deleted


def invalidate_terminology_resolution_caches(reason: str = "") -> dict[str, Any]:
    """Best-effort invalidation for all cached terminology resolve outputs."""
    try:
        import redis

        client = redis.from_url(
            os.getenv("REDIS_URL", _DEFAULT_REDIS_URL),
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.5,
            retry_on_timeout=False,
        )
        patterns = _cache_patterns()
        deleted = sum(_delete_pattern(client, pattern) for pattern in patterns)
        logger.info(
            "Invalidated terminology resolve caches deleted=%d reason=%s",
            deleted,
            reason,
        )
        return {"deleted": deleted, "patterns": patterns}
    except Exception as exc:
        logger.warning(
            "Terminology cache invalidation failed reason=%s error=%s",
            reason,
            exc,
            exc_info=True,
        )
        return {"deleted": 0, "error": str(exc), "patterns": _cache_patterns()}
