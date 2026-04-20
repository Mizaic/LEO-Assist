"""Factory to create the appropriate message bus adapter.

Atlas trace:
  DO: DO-245F62CB
  DI: DI-091CBBAB, DI-176EA4FF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-245F62CB")
"""

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
