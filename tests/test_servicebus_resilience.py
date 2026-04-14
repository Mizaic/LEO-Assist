from __future__ import annotations

import pytest

from libs.message_bus.azure_adapter import AzureServiceBusAdapter
from libs.message_bus.azure_adapter import (
    _MAX_RECONNECT_BACKOFF_SECONDS,
    _RECONNECT_BASE_DELAY_SECONDS,
    _is_unrecoverable_credential_error,
    _reconnect_backoff_seconds,
)


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
