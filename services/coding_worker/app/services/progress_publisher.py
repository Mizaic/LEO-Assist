"""Publish pipeline progress events to Redis pub/sub.

The Core API subscribes to the channel and relays events to the
browser via SSE (Server-Sent Events).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.from_url(redis_url)
    return _redis_client


def publish_progress(run_id: str, payload: dict[str, Any]) -> None:
    """Publish a progress event to Redis channel ``pipeline:{run_id}``."""
    try:
        r = _get_redis()
        channel = f"pipeline:{run_id}"
        r.publish(channel, json.dumps(payload, default=str))
    except Exception:
        logger.debug("Failed to publish progress to Redis", exc_info=True)
