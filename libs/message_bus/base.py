"""Abstract base class for message bus adapters."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


@dataclass
class Message:
    body: Dict[str, Any]
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    subject: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MessageBusAdapter(ABC):
    @abstractmethod
    async def send(self, queue_or_topic: str, message: Message) -> None: ...

    @abstractmethod
    async def subscribe(
        self,
        queue_or_topic: str,
        handler: Callable[[Message], Any],
        *,
        subscription: Optional[str] = None,
    ) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...
