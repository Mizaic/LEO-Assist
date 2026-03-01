"""
Shared DefaultAzureCredential singleton.

In Azure Container Apps: resolves via the user-assigned managed identity
(AZURE_CLIENT_ID env var must be set to the identity's client ID).

Locally: resolves via 'az login' -- no code changes required.
"""
from __future__ import annotations

from azure.identity import DefaultAzureCredential

_credential: DefaultAzureCredential | None = None


def get_credential() -> DefaultAzureCredential:
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential
