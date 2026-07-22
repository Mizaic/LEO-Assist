"""Azure Service Bus adapter for production message bus.

Atlas trace:
  DO: DO-2C7DDA31
  DI: DI-A3EF22B4
  VT: VT-8F4CEC33
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C7DDA31")

Uses AutoLockRenewer so long-running jobs (30+ minutes) don't lose their
message lock and get redelivered to another worker replica mid-processing.

Senders are cached per queue but guarded by a per-queue asyncio lock so
concurrent durable-step publishes cannot race on one AMQP session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from libs.message_bus.base import Message, MessageBusAdapter
from libs.message_bus.settlement import MessageDeferError, log_settlement_event

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

# Default max concurrent message handlers per receiver. Container Apps
# replicas are vertically scaled (multiple cores), so processing one
# message at a time per replica leaves CPU + LLM I/O parallelism on the
# table. Tunable via SB_MAX_CONCURRENT_CALLS.
_MAX_CONCURRENT_CALLS = max(1, int(os.getenv("SB_MAX_CONCURRENT_CALLS", "8")))
_SHUTDOWN_DRAIN_SECONDS = max(1, int(os.getenv("SB_SHUTDOWN_DRAIN_SECONDS", "120")))


def _is_dead_connection_error(exc: Exception) -> bool:
    """Return True when settlement failed because the AMQP session is gone."""
    seen: set[int] = set()
    current: Exception | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if "nonetype" in text and "_connection" in text:
            return True
        if isinstance(current, AttributeError) and "_connection" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def _reconnect_backoff_seconds(attempt: int) -> int:
    if attempt <= 1:
        return _RECONNECT_BASE_DELAY_SECONDS
    delay = _RECONNECT_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    return min(delay, _MAX_RECONNECT_BACKOFF_SECONDS)


class AzureServiceBusAdapter(MessageBusAdapter):
    def __init__(self, fully_qualified_namespace: str) -> None:
        from azure.servicebus.aio import ServiceBusClient

        connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "").strip()
        if connection_string:
            self._client = ServiceBusClient.from_connection_string(
                connection_string, uamqp_transport=False
            )
        else:
            from libs.azure.credentials import get_async_credential

            try:
                credential = get_async_credential()
            except ImportError as exc:
                raise RuntimeError(
                    "Async Azure credential unavailable. Install aiohttp or "
                    "set AZURE_SERVICE_BUS_CONNECTION_STRING."
                ) from exc

            self._client = ServiceBusClient(
                fully_qualified_namespace=fully_qualified_namespace,
                credential=credential,
                uamqp_transport=False,
            )
        self._senders: dict[str, Any] = {}
        self._sender_locks: dict[str, asyncio.Lock] = {}
        self._receivers: list[Any] = []
        self._tasks: list[Any] = []
        self._in_flight: set[asyncio.Task[Any]] = set()
        self._close_lock = asyncio.Lock()
        self._closed = False

    def _sender_lock(self, queue_or_topic: str) -> asyncio.Lock:
        """Return the per-queue lock used to serialise send + eviction."""
        lock = self._sender_locks.get(queue_or_topic)
        if lock is None:
            lock = asyncio.Lock()
            self._sender_locks[queue_or_topic] = lock
        return lock

    async def _evict_sender(self, queue_or_topic: str) -> None:
        """Drop a cached sender and close it so the AMQP session cannot be reused."""
        sender = self._senders.pop(queue_or_topic, None)
        if sender is None:
            return
        try:
            await sender.close()
        except Exception:
            logger.debug(
                "Sender close failed during eviction for %r",
                queue_or_topic,
                exc_info=True,
            )

    async def send(
        self,
        queue_or_topic: str,
        message: Message,
        *,
        schedule_after_seconds: int | None = None,
    ) -> None:
        from azure.servicebus import ServiceBusMessage
        from azure.servicebus.exceptions import (
            ServiceBusAuthenticationError,
            ServiceBusError,
        )

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
        # Concurrent durable steps share one cached sender per queue. Without
        # this lock, one failed send can tear down the AMQP session while
        # another coroutine still holds the same sender reference.
        async with self._sender_lock(queue_or_topic):
            for attempt in range(2):
                if queue_or_topic not in self._senders:
                    self._senders[queue_or_topic] = self._client.get_queue_sender(
                        queue_or_topic
                    )
                sender = self._senders[queue_or_topic]
                try:
                    await sender.send_messages(sb_msg)
                    return
                except ServiceBusAuthenticationError:
                    await self._evict_sender(queue_or_topic)
                    logger.error(
                        "Service Bus auth error sending to %r -- sender evicted "
                        "from cache. Check that AZURE_SERVICE_BUS_CONNECTION_STRING "
                        "uses a namespace-level SAS key with Send permission, or "
                        "that the managed identity has Azure Service Bus Data "
                        "Sender role on this queue.",
                        queue_or_topic,
                    )
                    raise
                except ServiceBusError:
                    # The AMQP session can become None after a connection drop
                    # (AttributeError: 'NoneType' has no attribute
                    # 'create_sender_link'). Evict + close so the next attempt
                    # opens a fresh sender.
                    await self._evict_sender(queue_or_topic)
                    if attempt == 1:
                        raise
                    logger.warning(
                        "Service Bus sender dead for %r (attempt %d) -- "
                        "evicting and retrying with fresh sender",
                        queue_or_topic,
                        attempt + 1,
                    )

    async def _settle_message(
        self, receiver: Any, sb_msg: Any, action: str, queue_or_topic: str
    ) -> None:
        """Complete or abandon a message, swallowing dead-connection errors on shutdown."""
        from azure.servicebus.exceptions import MessageLockLostError, ServiceBusError

        if self._closed:
            logger.info(
                "Shutdown in progress -- skipping %s for message %s on %s",
                action,
                sb_msg.message_id,
                queue_or_topic,
            )
            return
        try:
            if action == "complete":
                await receiver.complete_message(sb_msg)
                logger.info("Message %s completed", sb_msg.message_id)
            else:
                await receiver.abandon_message(sb_msg)
        except MessageLockLostError:
            logger.warning(
                "Message %s lock expired during %s -- Service Bus will redeliver",
                sb_msg.message_id,
                action,
            )
        except (ServiceBusError, AttributeError) as exc:
            if self._closed or _is_dead_connection_error(exc):
                logger.debug(
                    "Settlement %s skipped for message %s on %s during shutdown: %s",
                    action,
                    sb_msg.message_id,
                    queue_or_topic,
                    exc,
                )
                return
            raise

    async def _drain_in_flight(self) -> None:
        """Wait for active message handlers before closing AMQP connections."""
        pending = set(self._in_flight)
        if not pending:
            return
        logger.info(
            "Waiting for %d in-flight Service Bus handler(s) to finish",
            len(pending),
        )
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=_SHUTDOWN_DRAIN_SECONDS,
            )
        except asyncio.TimeoutError:
            still_running = sum(1 for task in pending if not task.done())
            logger.warning(
                "Service Bus shutdown drain timed out after %ss with %d handler(s) "
                "still running",
                _SHUTDOWN_DRAIN_SECONDS,
                still_running,
            )

    async def subscribe(
        self,
        queue_or_topic: str,
        handler: Callable[[Message], Any],
        *,
        subscription: Optional[str] = None,
    ) -> None:
        from azure.servicebus.aio import AutoLockRenewer
        from azure.servicebus.exceptions import MessageLockLostError, ServiceBusError

        sem = asyncio.Semaphore(_MAX_CONCURRENT_CALLS)

        async def _process_one(receiver: Any, sb_msg: Any) -> None:
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
                log_settlement_event(
                    "complete",
                    message_id=str(sb_msg.message_id or ""),
                    reason="handler_success",
                )
                await self._settle_message(receiver, sb_msg, "complete", queue_or_topic)
            except MessageDeferError as defer:
                log_settlement_event(
                    "abandon",
                    message_id=str(sb_msg.message_id or ""),
                    reason=defer.reason,
                    **defer.context,
                )
                if not self._closed:
                    await self._settle_message(
                        receiver, sb_msg, "abandon", queue_or_topic
                    )
            except MessageLockLostError:
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
                log_settlement_event(
                    "abandon",
                    message_id=str(sb_msg.message_id or ""),
                    reason="handler_exception",
                )
                if not self._closed:
                    await self._settle_message(
                        receiver, sb_msg, "abandon", queue_or_topic
                    )
            finally:
                sem.release()

        async def _handle_receiver_messages(receiver: Any, renewer: Any) -> None:
            # Pull messages off the receiver and dispatch them concurrently
            # up to _MAX_CONCURRENT_CALLS. Each message is registered with
            # the AutoLockRenewer immediately so locks survive the wait
            # for a free semaphore slot.
            async for sb_msg in receiver:
                if self._closed:
                    break
                renewer.register(
                    receiver,
                    sb_msg,
                    max_lock_renewal_duration=_MAX_LOCK_RENEWAL_SECONDS,
                )
                await sem.acquire()
                if self._closed:
                    sem.release()
                    break
                task = asyncio.create_task(_process_one(receiver, sb_msg))
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)

        async def _loop() -> None:
            attempts = 0

            try:
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
                        if self._closed:
                            break
                        attempts += 1
                        delay_s = _reconnect_backoff_seconds(attempts)
                        _log_servicebus_connection_error(exc, queue_or_topic, delay_s)
                        if _is_unrecoverable_credential_error(exc):
                            raise
                        await asyncio.sleep(delay_s)
                    except Exception:
                        if self._closed:
                            break
                        attempts += 1
                        delay_s = _reconnect_backoff_seconds(attempts)
                        logger.exception(
                            "Unexpected listener error for %s -- retrying in %ss",
                            queue_or_topic,
                            delay_s,
                        )
                        await asyncio.sleep(delay_s)
            finally:
                await self._drain_in_flight()

        task = asyncio.create_task(_loop())
        self._tasks.append(task)
        task.add_done_callback(lambda t: _on_listener_task_done(t, queue_or_topic))

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed and not self._tasks and not self._in_flight:
                return
            self._closed = True
            listener_tasks = list(self._tasks)
            for task in listener_tasks:
                task.cancel()
            if listener_tasks:
                await asyncio.gather(*listener_tasks, return_exceptions=True)
            self._tasks.clear()
            await self._drain_in_flight()
            for queue_name in list(self._senders.keys()):
                await self._evict_sender(queue_name)
            self._sender_locks.clear()
            for receiver in self._receivers:
                try:
                    await receiver.close()
                except Exception:
                    logger.debug("Receiver close failed during shutdown", exc_info=True)
            self._receivers.clear()
            try:
                await self._client.close()
            except Exception:
                logger.debug("Service Bus client close failed", exc_info=True)
