"""In-memory bus that records Service Bus-style settlement actions."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from libs.message_bus.base import Message, MessageBusAdapter
from libs.message_bus.settlement import MessageDeferError

logger = logging.getLogger(__name__)


@dataclass
class SettlementRecord:
    completed: list[str] = field(default_factory=list)
    abandoned: list[str] = field(default_factory=list)


class SettlementTrackingBus(MessageBusAdapter):
    """Queue adapter that completes or abandons like Azure Service Bus."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Message]] = defaultdict(asyncio.Queue)
        self._tasks: list[asyncio.Task[Any]] = []
        self.settlement = SettlementRecord()

    async def send(
        self,
        queue_or_topic: str,
        message: Message,
        *,
        schedule_after_seconds: int | None = None,
    ) -> None:
        await self._queues[queue_or_topic].put(message)

    async def subscribe(
        self,
        queue_or_topic: str,
        handler: Callable[[Message], Any],
        *,
        subscription: Optional[str] = None,
    ) -> None:
        queue = self._queues[queue_or_topic]

        async def _consume() -> None:
            while True:
                msg = await queue.get()
                try:
                    result = handler(msg)
                    if hasattr(result, "__await__"):
                        await result
                    self.settlement.completed.append(msg.message_id)
                except MessageDeferError:
                    self.settlement.abandoned.append(msg.message_id)
                except Exception:
                    logger.exception("Handler failed for %s", msg.message_id)
                    self.settlement.abandoned.append(msg.message_id)

        self._tasks.append(asyncio.create_task(_consume()))

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._queues.clear()
