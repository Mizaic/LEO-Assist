from __future__ import annotations

import asyncio

import pytest

from libs.message_bus.azure_adapter import AzureServiceBusAdapter
from libs.message_bus.azure_adapter import (
    _MAX_RECONNECT_BACKOFF_SECONDS,
    _RECONNECT_BASE_DELAY_SECONDS,
    _is_dead_connection_error,
    _is_unrecoverable_credential_error,
    _reconnect_backoff_seconds,
)
from libs.message_bus.base import Message


def test_reconnect_backoff_uses_base_delay_on_first_attempt() -> None:
    assert _reconnect_backoff_seconds(1) == _RECONNECT_BASE_DELAY_SECONDS


def test_reconnect_backoff_grows_and_caps() -> None:
    assert _reconnect_backoff_seconds(2) >= _RECONNECT_BASE_DELAY_SECONDS
    assert _reconnect_backoff_seconds(100) == _MAX_RECONNECT_BACKOFF_SECONDS


def test_unrecoverable_credential_error_detects_unicode_decode_chain() -> None:
    root = UnicodeDecodeError("utf-8", b"\xa0", 0, 1, "invalid start byte")
    exc = RuntimeError("credential failure")
    exc.__cause__ = root
    assert _is_unrecoverable_credential_error(exc) is True


def test_unrecoverable_credential_error_false_for_generic_exception() -> None:
    exc = RuntimeError("socket timeout")
    assert _is_unrecoverable_credential_error(exc) is False


def test_dead_connection_error_detects_none_connection_attribute() -> None:
    exc = RuntimeError(
        "Handler failed: 'NoneType' object has no attribute '_connection'"
    )
    assert _is_dead_connection_error(exc) is True


def test_dead_connection_error_detects_chained_attribute_error() -> None:
    root = AttributeError("'NoneType' object has no attribute '_connection'")
    exc = RuntimeError("settlement failed")
    exc.__cause__ = root
    assert _is_dead_connection_error(exc) is True


def test_adapter_uses_connection_string_when_available(monkeypatch) -> None:
    pytest.importorskip("azure.servicebus.aio")
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_CONNECTION_STRING",
        "Endpoint=sb://test.servicebus.windows.net/;"
        "SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=test",
    )

    called = {"used_conn_string": False}

    class _FakeClient:
        @staticmethod
        def from_connection_string(connection_string, uamqp_transport=False):
            called["used_conn_string"] = True
            assert "Endpoint=sb://test.servicebus.windows.net/" in connection_string
            assert uamqp_transport is False
            return object()

    monkeypatch.setattr("azure.servicebus.aio.ServiceBusClient", _FakeClient)

    adapter = AzureServiceBusAdapter("unused.servicebus.windows.net")
    assert adapter is not None
    assert called["used_conn_string"] is True


def test_adapter_raises_clear_error_when_async_credential_unavailable(
    monkeypatch,
) -> None:
    pytest.importorskip("azure.servicebus.aio")
    pytest.importorskip("azure.identity")
    monkeypatch.delenv("AZURE_SERVICE_BUS_CONNECTION_STRING", raising=False)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

    monkeypatch.setattr("azure.servicebus.aio.ServiceBusClient", _FakeClient)
    monkeypatch.setattr(
        "libs.azure.credentials.get_async_credential",
        lambda: (_ for _ in ()).throw(ImportError("aiohttp package is not installed")),
    )

    with pytest.raises(
        RuntimeError, match="Install aiohttp or set AZURE_SERVICE_BUS_CONNECTION_STRING"
    ):
        AzureServiceBusAdapter("test.servicebus.windows.net")


def _adapter_with_fake_client(monkeypatch, client: object) -> AzureServiceBusAdapter:
    """Build an adapter that uses a provided fake ServiceBusClient."""
    pytest.importorskip("azure.servicebus.aio")
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_CONNECTION_STRING",
        "Endpoint=sb://test.servicebus.windows.net/;"
        "SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=test",
    )

    class _ClientFactory:
        @staticmethod
        def from_connection_string(connection_string, uamqp_transport=False):
            _ = connection_string, uamqp_transport
            return client

    monkeypatch.setattr("azure.servicebus.aio.ServiceBusClient", _ClientFactory)
    return AzureServiceBusAdapter("unused.servicebus.windows.net")


@pytest.mark.asyncio
async def test_send_serialises_concurrent_calls_on_shared_sender(monkeypatch) -> None:
    """Concurrent sends must not overlap on the cached sender."""
    from azure.servicebus.exceptions import ServiceBusError

    active = 0
    max_active = 0
    fail_once = {"done": False}

    class _FakeSender:
        def __init__(self) -> None:
            self.closed = False
            self.sends = 0

        async def send_messages(self, _msg) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            self.sends += 1
            active -= 1
            if not fail_once["done"]:
                fail_once["done"] = True
                raise ServiceBusError("simulated dead session")

        async def close(self) -> None:
            self.closed = True

    senders: list[_FakeSender] = []

    class _FakeClient:
        def get_queue_sender(self, _queue: str) -> _FakeSender:
            sender = _FakeSender()
            senders.append(sender)
            return sender

    adapter = _adapter_with_fake_client(monkeypatch, _FakeClient())
    msg = Message(body={"ok": True}, message_id="m1")

    await asyncio.gather(
        adapter.send("pipeline-jobs", msg),
        adapter.send("pipeline-jobs", Message(body={"ok": True}, message_id="m2")),
        adapter.send("pipeline-jobs", Message(body={"ok": True}, message_id="m3")),
    )

    assert max_active == 1
    assert all(s.closed or s is adapter._senders.get("pipeline-jobs") for s in senders)
    assert len(senders) >= 2
    assert sum(s.sends for s in senders) >= 3


@pytest.mark.asyncio
async def test_send_evicts_and_closes_dead_sender(monkeypatch) -> None:
    """A dead sender is closed before a fresh sender is opened."""
    from azure.servicebus.exceptions import ServiceBusError

    class _FakeSender:
        def __init__(self, *, fail: bool) -> None:
            self.fail = fail
            self.closed = False

        async def send_messages(self, _msg) -> None:
            if self.fail:
                raise ServiceBusError("dead")

        async def close(self) -> None:
            self.closed = True

    created: list[_FakeSender] = []

    class _FakeClient:
        def get_queue_sender(self, _queue: str) -> _FakeSender:
            sender = _FakeSender(fail=len(created) == 0)
            created.append(sender)
            return sender

    adapter = _adapter_with_fake_client(monkeypatch, _FakeClient())
    await adapter.send("pipeline-jobs", Message(body={"ok": True}, message_id="m1"))

    assert len(created) == 2
    assert created[0].closed is True
    assert created[1].closed is False
    assert adapter._senders["pipeline-jobs"] is created[1]


@pytest.mark.asyncio
async def test_close_waits_for_in_flight_handlers(monkeypatch) -> None:
    """Shutdown must drain active handlers before closing the client."""

    class _FakeClient:
        async def close(self) -> None:
            return None

    adapter = _adapter_with_fake_client(monkeypatch, _FakeClient())
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_handler() -> None:
        started.set()
        await release.wait()

    in_flight = asyncio.create_task(slow_handler())
    adapter._in_flight.add(in_flight)
    in_flight.add_done_callback(adapter._in_flight.discard)
    close_task = asyncio.create_task(adapter.close())

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert close_task.done() is False
    release.set()
    await asyncio.wait_for(close_task, timeout=2.0)
    assert adapter._closed is True
    assert not adapter._in_flight


@pytest.mark.asyncio
async def test_settle_swallows_dead_connection_error(monkeypatch) -> None:
    from azure.servicebus.exceptions import ServiceBusError

    class _FakeReceiver:
        def __init__(self) -> None:
            self.complete_calls = 0

        async def complete_message(self, _msg) -> None:
            self.complete_calls += 1
            raise ServiceBusError(
                "Handler failed: 'NoneType' object has no attribute '_connection'"
            )

    adapter = _adapter_with_fake_client(monkeypatch, object())
    receiver = _FakeReceiver()
    msg = type("Msg", (), {"message_id": "m-dead-session"})()

    await adapter._settle_message(receiver, msg, "complete", "pipeline-jobs")

    assert receiver.complete_calls == 1


@pytest.mark.asyncio
async def test_settle_skips_abandon_when_shutdown_flag_set(monkeypatch) -> None:
    from azure.servicebus.exceptions import ServiceBusError

    class _FakeReceiver:
        def __init__(self) -> None:
            self.abandon_calls = 0

        async def abandon_message(self, _msg) -> None:
            self.abandon_calls += 1
            raise ServiceBusError(
                "Handler failed: 'NoneType' object has no attribute '_connection'"
            )

    adapter = _adapter_with_fake_client(monkeypatch, object())
    adapter._closed = True
    receiver = _FakeReceiver()
    msg = type("Msg", (), {"message_id": "m-shutdown"})()

    await adapter._settle_message(receiver, msg, "abandon", "pipeline-jobs")

    assert receiver.abandon_calls == 0
