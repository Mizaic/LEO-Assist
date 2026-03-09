"""In-memory queue adapter for local development (no Azure Service Bus needed)."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Optional

from libs.message_bus.base import Message, MessageBusAdapter

logger = logging.getLogger("libs.message_bus.in_memory")


class InMemoryQueueAdapter(MessageBusAdapter):
    """Simple asyncio.Queue-based message bus for local dev and testing."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Message]] = defaultdict(asyncio.Queue)
        self._tasks: list[asyncio.Task] = []

    async def send(
        self,
        queue_or_topic: str,
        message: Message,
        *,
        schedule_after_seconds: int | None = None,
    ) -> None:
        async def _enqueue() -> None:
            if schedule_after_seconds and schedule_after_seconds > 0:
                await asyncio.sleep(schedule_after_seconds)
            await self._queues[queue_or_topic].put(message)
            logger.debug("Enqueued message %s on %s", message.message_id, queue_or_topic)

        if schedule_after_seconds and schedule_after_seconds > 0:
            task = asyncio.create_task(_enqueue())
            self._tasks.append(task)
            return
        await _enqueue()

    async def subscribe(
        self,
        queue_or_topic: str,
        handler: Callable[[Message], Any],
        *,
        subscription: Optional[str] = None,
    ) -> None:
        queue = self._queues[queue_or_topic]

        async def _consume():
            while True:
                msg = await queue.get()
                try:
                    result = handler(msg)
                    if hasattr(result, "__await__"):
                        await result
                except Exception:
                    logger.exception("Handler failed for %s", msg.message_id)

        task = asyncio.create_task(_consume())
        self._tasks.append(task)

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        self._queues.clear()
