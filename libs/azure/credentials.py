"""
Shared credential singletons for sync and async Azure SDK clients.

In Azure Container Apps: resolves via the user-assigned managed identity
(AZURE_CLIENT_ID env var must be set to the identity's client ID).

Locally: resolves via 'az login' -- no code changes required.

Use get_credential() for sync clients (Key Vault, Blob Storage, etc.).
Use get_async_credential() for async clients (Service Bus aio, etc.).
"""

from __future__ import annotations

from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

_credential: DefaultAzureCredential | None = None
_async_credential: AsyncDefaultAzureCredential | None = None


def get_credential() -> DefaultAzureCredential:
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def get_async_credential() -> AsyncDefaultAzureCredential:
    global _async_credential
    if _async_credential is None:
        _async_credential = AsyncDefaultAzureCredential()
    return _async_credential
