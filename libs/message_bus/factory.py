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
    """Return an Azure adapter when Service Bus is configured, else in-memory."""
    from libs.message_bus.runtime_config import (
        connection_string_endpoint,
        normalize_service_bus_host,
    )

    namespace = normalize_service_bus_host(
        os.getenv("AZURE_SERVICE_BUS_NAMESPACE", "").strip() or None
    )
    connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "").strip()

    if not namespace and connection_string:
        namespace = normalize_service_bus_host(
            connection_string_endpoint(connection_string)
        )

    if namespace or connection_string:
        from libs.message_bus.azure_adapter import AzureServiceBusAdapter

        return AzureServiceBusAdapter(namespace or "")

    from libs.message_bus.in_memory_adapter import InMemoryQueueAdapter

    return InMemoryQueueAdapter()
