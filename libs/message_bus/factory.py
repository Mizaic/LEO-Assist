"""Factory to create the appropriate message bus adapter."""

from __future__ import annotations

import os

from libs.message_bus.base import MessageBusAdapter


def create_message_bus() -> MessageBusAdapter:
    """Return an Azure adapter when the Service Bus namespace is configured, else in-memory."""
    namespace = os.getenv("AZURE_SERVICE_BUS_NAMESPACE")
    if namespace:
        from libs.message_bus.azure_adapter import AzureServiceBusAdapter

        return AzureServiceBusAdapter(namespace)

    from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter

    return InMemoryQueueAdapter()
