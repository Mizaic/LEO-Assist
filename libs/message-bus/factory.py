"""Factory to create the appropriate message bus adapter."""

from __future__ import annotations

import os

from libs.message_bus.base import MessageBusAdapter


def create_message_bus() -> MessageBusAdapter:
    """Return an Azure adapter when connection string is set, else in-memory."""
    conn_str = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING")
    if conn_str:
        from libs.message_bus.azure_adapter import AzureServiceBusAdapter

        return AzureServiceBusAdapter(conn_str)

    from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter

    return InMemoryQueueAdapter()
