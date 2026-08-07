"""Tests for message bus factory adapter selection."""

from __future__ import annotations

from libs.message_bus.factory import create_message_bus
from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter


def test_create_message_bus_uses_in_memory_without_config(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_SERVICE_BUS_NAMESPACE", raising=False)
    monkeypatch.delenv("AZURE_SERVICE_BUS_CONNECTION_STRING", raising=False)

    bus = create_message_bus()

    assert isinstance(bus, InMemoryQueueAdapter)


def test_create_message_bus_uses_azure_when_namespace_set(monkeypatch) -> None:
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_NAMESPACE",
        "leoai-val-bus.servicebus.windows.net",
    )
    monkeypatch.delenv("AZURE_SERVICE_BUS_CONNECTION_STRING", raising=False)

    created: dict[str, str] = {}

    class _FakeAzureAdapter:
        def __init__(self, namespace: str) -> None:
            created["namespace"] = namespace

    monkeypatch.setattr(
        "libs.message_bus.azure_adapter.AzureServiceBusAdapter",
        _FakeAzureAdapter,
    )

    bus = create_message_bus()

    assert isinstance(bus, _FakeAzureAdapter)
    assert created["namespace"] == "leoai-val-bus.servicebus.windows.net"


def test_create_message_bus_uses_azure_when_connection_string_only(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AZURE_SERVICE_BUS_NAMESPACE", raising=False)
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_CONNECTION_STRING",
        "Endpoint=sb://leoai-val-bus.servicebus.windows.net/;"
        "SharedAccessKeyName=rule;SharedAccessKey=secret",
    )

    created: dict[str, str] = {}

    class _FakeAzureAdapter:
        def __init__(self, namespace: str) -> None:
            created["namespace"] = namespace

    monkeypatch.setattr(
        "libs.message_bus.azure_adapter.AzureServiceBusAdapter",
        _FakeAzureAdapter,
    )

    bus = create_message_bus()

    assert isinstance(bus, _FakeAzureAdapter)
    assert created["namespace"] == "leoai-val-bus.servicebus.windows.net"
