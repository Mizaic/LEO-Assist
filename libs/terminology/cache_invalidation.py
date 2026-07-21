"""Terminology cache invalidation helpers.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

SurfaceForm changes alter the resolver's source of truth. Any cached
resolution result may therefore be stale after a mapping is added, approved,
deleted, deduplicated, or deactivated.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_REDIS_URL = "redis://localhost:6379"
_DEFAULT_CLIENT_CACHE_PREFIX = "terminology:api:v3:"
_RESOLVER_CACHE_PATTERN = "term_resolve:v1:*"
_CLIENT_RESOLVE_CACHE_PATTERN = "terminology:api:*:resolve:*"
_DELETE_BATCH_SIZE = 500


def _cache_patterns() -> tuple[str, ...]:
    client_prefix = os.getenv(
        "TERMINOLOGY_CACHE_PREFIX",
        _DEFAULT_CLIENT_CACHE_PREFIX,
    )
    patterns = {
        _RESOLVER_CACHE_PATTERN,
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
