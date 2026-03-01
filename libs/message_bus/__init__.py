"""Message bus abstraction layer.

Provides a unified interface for message publishing/consuming with two backends:
- AzureServiceBusAdapter: for production (Azure Service Bus cloud service)
- InMemoryQueueAdapter: for local development (no cloud dependency)
"""

from libs.message_bus.base import MessageBusAdapter, Message
from libs.message_bus.factory import create_message_bus

__all__ = ["MessageBusAdapter", "Message", "create_message_bus"]
