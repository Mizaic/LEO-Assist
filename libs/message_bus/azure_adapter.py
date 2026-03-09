"""Azure Service Bus adapter for production message bus.

Uses AutoLockRenewer so long-running jobs (30+ minutes) don't lose their
message lock and get redelivered to another worker replica mid-processing.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from libs.message_bus.base import Message, MessageBusAdapter

logger = logging.getLogger("libs.message_bus.azure")

# Maximum time in seconds to keep renewing a message lock.
# Set generously — a patient with 300 clinical encounters can take 2+ hours.
_MAX_LOCK_RENEWAL_SECONDS = int(os.getenv("SB_MAX_LOCK_RENEWAL_SECONDS", "14400"))  # 4 hours


class AzureServiceBusAdapter(MessageBusAdapter):
    def __init__(self, fully_qualified_namespace: str) -> None:
        from azure.servicebus.aio import ServiceBusClient
        from libs.azure.credentials import get_async_credential

        self._client = ServiceBusClient(
            fully_qualified_namespace=fully_qualified_namespace,
            credential=get_async_credential(),
            uamqp_transport=False,
        )
        self._senders: dict[str, Any] = {}
        self._receivers: list[Any] = []

    async def send(
        self,
        queue_or_topic: str,
        message: Message,
        *,
        schedule_after_seconds: int | None = None,
    ) -> None:
        from azure.servicebus import ServiceBusMessage

        if queue_or_topic not in self._senders:
            self._senders[queue_or_topic] = self._client.get_queue_sender(
                queue_or_topic
            )
        sender = self._senders[queue_or_topic]
        sb_msg = ServiceBusMessage(
            body=json.dumps(message.body),
            message_id=message.message_id,
            correlation_id=message.correlation_id,
            subject=message.subject,
            scheduled_enqueue_time_utc=(
                datetime.now(timezone.utc) + timedelta(seconds=schedule_after_seconds)
                if schedule_after_seconds and schedule_after_seconds > 0
                else None
            ),
        )
        await sender.send_messages(sb_msg)

    async def subscribe(
        self,
        queue_or_topic: str,
        handler: Callable[[Message], Any],
        *,
        subscription: Optional[str] = None,
    ) -> None:
        import asyncio
        from azure.servicebus.aio import AutoLockRenewer

        if subscription:
            receiver = self._client.get_subscription_receiver(
                topic_name=queue_or_topic,
                subscription_name=subscription,
            )
        else:
            receiver = self._client.get_queue_receiver(queue_or_topic)
        self._receivers.append(receiver)

        async def _loop():
            from azure.servicebus.exceptions import MessageLockLostError

            async with AutoLockRenewer() as renewer:
                async with receiver:
                    async for sb_msg in receiver:
                        # Register this message for automatic lock renewal.
                        # If the worker crashes, renewal stops and the lock
                        # expires naturally so another replica can pick it up.
                        renewer.register(
                            receiver,
                            sb_msg,
                            max_lock_renewal_duration=_MAX_LOCK_RENEWAL_SECONDS,
                        )
                        try:
                            body = json.loads(str(sb_msg))
                            msg = Message(
                                body=body,
                                message_id=sb_msg.message_id or "",
                                correlation_id=sb_msg.correlation_id,
                                subject=sb_msg.subject,
                            )
                            logger.info(
                                "Message %s received from %s — lock auto-renewal active (max %ds)",
                                sb_msg.message_id, queue_or_topic, _MAX_LOCK_RENEWAL_SECONDS,
                            )
                            result = handler(msg)
                            if hasattr(result, "__await__"):
                                await result
                            await receiver.complete_message(sb_msg)
                            logger.info("Message %s completed", sb_msg.message_id)
                        except MessageLockLostError:
                            # Lock expired — Service Bus will redeliver automatically.
                            # There is nothing to settle; any attempt to complete/abandon
                            # will also raise MessageLockLostError.
                            logger.warning(
                                "Message %s lock expired before settlement — "
                                "Service Bus will redeliver (delivery count will increment)",
                                sb_msg.message_id,
                            )
                        except Exception:
                            logger.exception(
                                "Handler failed for message %s — abandoning (will retry)",
                                sb_msg.message_id,
                            )
                            try:
                                await receiver.abandon_message(sb_msg)
                            except MessageLockLostError:
                                logger.warning(
                                    "Message %s lock also expired during abandon — "
                                    "Service Bus will redeliver",
                                    sb_msg.message_id,
                                )

        asyncio.create_task(_loop())

    async def close(self) -> None:
        for sender in self._senders.values():
            await sender.close()
        await self._client.close()
