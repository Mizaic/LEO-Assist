"""Redis-backed distributed cache for terminology resolution."""

import json
import logging
import os
import hashlib
from typing import Any

logger = logging.getLogger(__name__)


def _build_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


class TerminologyCache:
    """Redis-backed cache for terminology lookups with MGET and pipelined SETEX."""

    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, url: str | None = None) -> None:
        import redis

        url = url or _build_redis_url()
        self._client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
        )

    def generate_key(
        self,
        term: str,
        expected_tag: str | None,
        enrich_lab_domain: bool,
        org_id: str | None = None,
        package_fingerprint: str = "",
    ) -> str:
        """Generate a deterministic composite cache key."""
        text_hash = hashlib.md5(term.strip().lower().encode("utf-8")).hexdigest()
        tag_str = (expected_tag or "").strip().lower()
        org_str = (org_id or "").strip() or "_"
        fp = (package_fingerprint or "").strip() or "_"
        return (
            f"term_resolve:v2:{text_hash}:{tag_str}:{enrich_lab_domain}"
            f":{org_str}:{fp}"
        )

    def mget(self, keys: list[str]) -> dict[str, Any]:
        """Fetch multiple cache keys, returning a dict mapping key to deserialized payload."""
        if not keys:
            return {}
        try:
            raw_values = self._client.mget(keys)
            results = {}
            for key, raw in zip(keys, raw_values):
                if raw is not None:
                    try:
                        results[key] = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
            return results
        except Exception:
            logger.warning("TerminologyCache MGET failed", exc_info=True)
            return {}

    def msetex(self, mapping: dict[str, Any], ttl: int = DEFAULT_TTL) -> None:
        """Write multiple key-value pairs to Redis using a pipeline, with a TTL."""
        if not mapping:
            return
        try:
            pipeline = self._client.pipeline(transaction=False)
            for key, value in mapping.items():
                pipeline.setex(key, ttl, json.dumps(value, default=str))
            pipeline.execute()
        except Exception:
            logger.warning("TerminologyCache pipelined SETEX failed", exc_info=True)
