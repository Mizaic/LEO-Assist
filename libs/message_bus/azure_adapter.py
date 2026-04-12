"""Azure Service Bus adapter for production message bus.

Uses AutoLockRenewer so long-running jobs (30+ minutes) don't lose their
message lock and get redelivered to another worker replica mid-processing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from libs.message_bus.base import Message, MessageBusAdapter

logger = logging.getLogger("libs.message_bus.azure")


def _is_unrecoverable_credential_error(exc: Exception) -> bool:
    """Return True when credential refresh cannot be retried automatically."""
    cause = exc.__cause__ or exc.__context__
    return isinstance(cause, UnicodeDecodeError)


def _log_servicebus_connection_error(exc: Exception, queue: str, delay_s: int) -> None:
    """Log a Service Bus connection error with next retry timing.

    The azure-identity library decodes az-CLI stderr as UTF-8.  On Windows,
    AAD error messages contain non-breaking spaces (0xa0 / Latin-1) which are
    not valid UTF-8, causing a UnicodeDecodeError when a token refresh is
    needed.  We detect that specific chain and emit a clear 'run az login'
    instruction instead of the raw codec error.
    """
    if _is_unrecoverable_credential_error(exc):
        logger.critical(
            "Azure credential token expired or could not be refreshed for %s.  "
            "Re-authenticate: az login --scope https://servicebus.azure.net//.default  "
            "Raw error: %s",
            queue,
            exc,
        )
    else:
        logger.warning(
            "Service Bus connection lost for %s -- retrying in %ss. Error: %s",
            queue,
            delay_s,
            exc,
        )


def _on_listener_task_done(task: "asyncio.Task[None]", queue: str) -> None:
    """Done callback that surfaces listener task exceptions."""
    if task.cancelled():
        logger.warning("Service Bus listener task for %s was cancelled", queue)
        return
    exc = task.exception()
    if exc is not None:
        logger.critical(
            "Service Bus listener for %s terminated with an unhandled exception: %s",
            queue,
            exc,
        )


# Maximum time in seconds to keep renewing a message lock.
# Set generously — a patient with 300 clinical encounters can take 2+ hours.
_MAX_LOCK_RENEWAL_SECONDS = int(
    os.getenv("SB_MAX_LOCK_RENEWAL_SECONDS", "14400")
)  # 4 hours
_RECONNECT_BASE_DELAY_SECONDS = max(
    1, int(os.getenv("SB_RECONNECT_BASE_DELAY_SECONDS", "5"))
)
_MAX_RECONNECT_BACKOFF_SECONDS = max(
    _RECONNECT_BASE_DELAY_SECONDS,
    int(os.getenv("SB_MAX_RECONNECT_BACKOFF_SECONDS", "60")),
)


def _reconnect_backoff_seconds(attempt: int) -> int:
    if attempt <= 1:
        return _RECONNECT_BASE_DELAY_SECONDS
    delay = _RECONNECT_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    return min(delay, _MAX_RECONNECT_BACKOFF_SECONDS)


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
        self._tasks: list[Any] = []
        self._closed = False

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
        from azure.servicebus.aio import AutoLockRenewer
        from azure.servicebus.exceptions import MessageLockLostError, ServiceBusError

        async def _handle_receiver_messages(receiver: Any, renewer: Any) -> None:
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
                        (
                            "Message %s received from %s -- "
                            "lock auto-renewal active (max %ds)"
                        ),
                        sb_msg.message_id,
                        queue_or_topic,
                        _MAX_LOCK_RENEWAL_SECONDS,
                    )
                    result = handler(msg)
                    if hasattr(result, "__await__"):
                        await result
                    await receiver.complete_message(sb_msg)
                    logger.info("Message %s completed", sb_msg.message_id)
                except MessageLockLostError:
                    # Lock expired -- Service Bus will redeliver automatically.
                    logger.warning(
                        "Message %s lock expired before settlement -- "
                        "Service Bus will redeliver (delivery count will increment)",
                        sb_msg.message_id,
                    )
                except Exception:
                    logger.exception(
                        "Handler failed for message %s -- abandoning (will retry)",
                        sb_msg.message_id,
                    )
                    try:
                        await receiver.abandon_message(sb_msg)
                    except MessageLockLostError:
                        logger.warning(
                            "Message %s lock also expired during abandon -- "
                            "Service Bus will redeliver",
                            sb_msg.message_id,
                        )

        async def _loop() -> None:
            attempts = 0

            while not self._closed:
                if subscription:
                    receiver = self._client.get_subscription_receiver(
                        topic_name=queue_or_topic,
                        subscription_name=subscription,
                    )
                else:
                    receiver = self._client.get_queue_receiver(queue_or_topic)
                self._receivers.append(receiver)

                try:
                    async with AutoLockRenewer() as renewer:
                        async with receiver:
                            attempts = 0
                            await _handle_receiver_messages(receiver, renewer)
                except asyncio.CancelledError:
                    raise
                except ServiceBusError as exc:
                    attempts += 1
                    delay_s = _reconnect_backoff_seconds(attempts)
                    _log_servicebus_connection_error(exc, queue_or_topic, delay_s)
                    if _is_unrecoverable_credential_error(exc):
                        raise
                    await asyncio.sleep(delay_s)
                except Exception:
                    attempts += 1
                    delay_s = _reconnect_backoff_seconds(attempts)
                    logger.exception(
                        "Unexpected listener error for %s -- retrying in %ss",
                        queue_or_topic,
                        delay_s,
                    )
                    await asyncio.sleep(delay_s)

        task = asyncio.create_task(_loop())
        self._tasks.append(task)
        task.add_done_callback(lambda t: _on_listener_task_done(t, queue_or_topic))

    async def close(self) -> None:
        self._closed = True
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        for sender in self._senders.values():
            await sender.close()
        for receiver in self._receivers:
            try:
                await receiver.close()
            except Exception:
                logger.debug("Receiver close failed during shutdown", exc_info=True)
        self._receivers.clear()
        await self._client.close()
