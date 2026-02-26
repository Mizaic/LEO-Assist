"""Tests for shared utility libraries (cache, message bus, auth)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


class TestLLMCache:

    def test_cache_set_and_get(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=100)
        messages = [{"role": "user", "content": "hello"}]
        cache.set(messages, "response-1")
        assert cache.get(messages) == "response-1"

    def test_cache_eviction(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=2)
        cache.set([{"role": "user", "content": "a"}], "1")
        cache.set([{"role": "user", "content": "b"}], "2")
        cache.set([{"role": "user", "content": "c"}], "3")
        assert cache.get([{"role": "user", "content": "a"}]) is None
        assert cache.get([{"role": "user", "content": "c"}]) == "3"

    def test_cache_stats(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=10)
        msgs = [{"role": "user", "content": "x"}]
        cache.set(msgs, "y")
        cache.get(msgs)
        cache.get([{"role": "user", "content": "miss"}])
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_cache_miss(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=10)
        assert cache.get([{"role": "user", "content": "not stored"}]) is None

    def test_cache_clear(self):
        from libs.llm_client.cache import InMemoryLLMCache

        cache = InMemoryLLMCache(max_size=10)
        cache.set([{"role": "user", "content": "x"}], "y")
        cache.clear()
        assert cache.stats()["size"] == 0


class TestMessageBus:

    @pytest.mark.asyncio
    async def test_in_memory_adapter(self):
        from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter
        from libs.message_bus.base import Message

        adapter = InMemoryQueueAdapter()
        received = []

        async def handler(msg):
            received.append(msg.body)

        await adapter.subscribe("test-queue", handler)
        await adapter.send("test-queue", Message(body={"key": "value"}))
        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0]["key"] == "value"
        await adapter.close()

    @pytest.mark.asyncio
    async def test_in_memory_multiple_messages(self):
        from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter
        from libs.message_bus.base import Message

        adapter = InMemoryQueueAdapter()
        received = []

        async def handler(msg):
            received.append(msg.body)

        await adapter.subscribe("q", handler)
        await adapter.send("q", Message(body={"n": 1}))
        await adapter.send("q", Message(body={"n": 2}))
        await asyncio.sleep(0.1)
        assert len(received) == 2
        await adapter.close()


class TestAuthLib:

    def test_tenant_context_creation(self):
        from libs.auth.tenant_context import TenantContext

        ctx = TenantContext(
            tenant_id="test-tenant",
            user_oid="user-123",
            roles="admin,reader",
            app_id="app-456",
        )
        assert ctx.tenant_id == "test-tenant"
        assert ctx.user_oid == "user-123"
        assert ctx.roles == "admin,reader"

    def test_tenant_context_defaults(self):
        from libs.auth.tenant_context import TenantContext

        ctx = TenantContext(tenant_id="t1")
        assert ctx.user_oid is None
        assert ctx.roles is None
        assert ctx.app_id is None
