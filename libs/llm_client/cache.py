"""LLM response caching with LRU eviction and optional TTL.

Ported from auditor_2 agent/core/llm_cache.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("libs.llm_client.cache")


class InMemoryLLMCache:
    """In-memory LRU cache for LLM responses with optional TTL expiration."""

    def __init__(
        self, max_size: int = 10_000, ttl_seconds: Optional[int] = None
    ) -> None:
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @staticmethod
    def _make_key(messages: List[Dict[str, Any]]) -> str:
        key_data = [
            {
                "role": msg.get("role") or msg.get("type", ""),
                "content": msg.get("content", ""),
            }
            for msg in messages
        ]
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def get(self, messages: List[Dict[str, Any]]) -> Optional[Any]:
        cache_key = self._make_key(messages)
        if cache_key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[cache_key]
        if self.ttl_seconds and entry.get("created_at"):
            age = (datetime.now() - entry["created_at"]).total_seconds()
            if age > self.ttl_seconds:
                del self._cache[cache_key]
                self._misses += 1
                return None

        self._cache.move_to_end(cache_key)
        self._hits += 1
        return entry.get("response")

    def set(self, messages: List[Dict[str, Any]], response: Any) -> None:
        cache_key = self._make_key(messages)
        if len(self._cache) >= self.max_size and cache_key not in self._cache:
            self._cache.popitem(last=False)
            self._evictions += 1

        self._cache[cache_key] = {
            "response": response,
            "created_at": datetime.now(),
        }
        self._cache.move_to_end(cache_key)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = self._misses = self._evictions = 0

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate_percent": round(self._hits / total * 100, 2) if total else 0.0,
            "total_requests": total,
        }


_global_cache: Optional[InMemoryLLMCache] = None


def get_llm_cache() -> InMemoryLLMCache:
    global _global_cache
    if _global_cache is None:
        max_size = int(os.getenv("LLM_CACHE_SIZE", "10000"))
        ttl = int(os.getenv("LLM_CACHE_TTL_SECONDS", "0")) or None
        _global_cache = InMemoryLLMCache(max_size=max_size, ttl_seconds=ttl)
        logger.info(
            "Initialized LLM cache: max_size=%d ttl=%s", max_size, ttl or "none"
        )
    return _global_cache


def clear_llm_cache() -> None:
    get_llm_cache().clear()
    logger.info("Cleared LLM cache")


def get_cache_stats() -> Dict[str, Any]:
    return get_llm_cache().stats()


def messages_to_dict(messages: List[Any]) -> List[Dict[str, Any]]:
    """Normalise LangChain messages / dicts into a list of role+content dicts."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        if hasattr(msg, "content") and hasattr(msg, "type"):
            content = msg.content
            if isinstance(content, list):
                content = " ".join(str(item) for item in content)
            elif not isinstance(content, str):
                content = str(content)
            result.append({"type": msg.type, "content": content})
        elif isinstance(msg, dict):
            normalised = dict(msg)
            if "content" in normalised and not isinstance(normalised["content"], str):
                normalised["content"] = str(normalised["content"])
            result.append(normalised)
        else:
            result.append(
                {
                    "type": getattr(msg, "type", "human"),
                    "content": str(getattr(msg, "content", msg)),
                }
            )
    return result


async def cached_llm_invoke(
    llm_func,
    messages: List[Any],
    *,
    cache_enabled: bool = True,
    **kwargs,
) -> Any:
    """Invoke an async LLM function with transparent caching."""
    if not cache_enabled:
        return await llm_func(messages, **kwargs)

    cache = get_llm_cache()
    msgs = messages_to_dict(messages)
    cached = cache.get(msgs)
    if cached is not None:
        logger.debug("Cache HIT")
        return cached

    logger.debug("Cache MISS")
    response = await llm_func(messages, **kwargs)
    cache.set(msgs, response)
    return response
