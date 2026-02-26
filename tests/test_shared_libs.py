"""Tests for shared libraries (libs/)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestLLMCache:
    """Tests for the in-memory LLM cache."""

    def test_cache_set_and_get(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.get("missing") is None

    def test_cache_eviction(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=2)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.set("c", "3")

        assert cache.get("a") is None
        assert cache.get("b") == "2"
        assert cache.get("c") == "3"

    def test_cache_stats(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=10)
        cache.set("x", "y")
        cache.get("x")
        cache.get("miss")

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1


class TestMessageBus:
    """Tests for the message bus abstraction."""

    @pytest.mark.asyncio
    async def test_in_memory_adapter(self):
        from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter
        from libs.message_bus.base import Message

        adapter = InMemoryQueueAdapter()
        received = []

        async def handler(msg: Message):
            received.append(msg)

        await adapter.subscribe("test-queue", handler)
        await adapter.publish("test-queue", Message(body={"key": "value"}))

        assert len(received) == 1
        assert received[0].body["key"] == "value"

    def test_message_bus_factory_local(self):
        from libs.message_bus.factory import create_message_bus

        with patch.dict("os.environ", {"AZURE_SERVICE_BUS_CONNECTION": ""}):
            bus = create_message_bus()
            assert bus.__class__.__name__ == "InMemoryQueueAdapter"


class TestAuthLib:
    """Tests for the shared auth library."""

    def test_tenant_context_creation(self):
        from libs.auth.tenant_context import TenantContext

        ctx = TenantContext(
            tenant_id="t1",
            user_id="u1",
            email="test@example.com",
            roles=["admin"],
        )
        assert ctx.tenant_id == "t1"
        assert "admin" in ctx.roles
