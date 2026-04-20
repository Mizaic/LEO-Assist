"""Unit tests for the Microsoft Graph on-behalf-of token exchange.

Pins the consent-failure detection that the admin portal relies on:
    DI-31F4C232 (the /admin/entra capability probe + 7 endpoints)
    DI-6CF7FCE0 (audited, never persisted, OBO only)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.graph_client.errors import GraphClientError, InsufficientConsent
from libs.graph_client.obo import (
    exchange_for_graph_token,
    obo_cache_key,
)


def _async_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body
    return resp


def _async_client(post_response):
    client = MagicMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=post_response)
    return client


def test_obo_cache_key_excludes_raw_email_and_scopes():
    key = obo_cache_key(
        email="alice@contoso.com",
        tenant_id="t1",
        scopes=["https://graph.microsoft.com/User.Read.All"],
    )
    assert "alice@contoso.com" not in key
    assert "User.Read.All" not in key
    assert key.startswith("obo:")
    assert ":t1:" in key


def test_obo_consent_failure_raises_insufficient_consent(monkeypatch):
    monkeypatch.setenv("DISABLE_REDIS", "true")
    body = {
        "error": "invalid_grant",
        "suberror": "consent_required",
        "error_description": "AADSTS65001: The user or administrator has not consented",
    }
    client = _async_client(_async_response(400, body))

    with pytest.raises(InsufficientConsent) as exc_info:
        asyncio.run(
            exchange_for_graph_token(
                user_token="u-token",
                tenant_id="t-1",
                scopes=["https://graph.microsoft.com/User.Read.All"],
                email="alice@contoso.com",
                http_client=client,
                use_cache=False,
            )
        )

    assert exc_info.value.status_code == 400
    assert "consent" in str(exc_info.value).lower()


def test_obo_other_error_raises_generic(monkeypatch):
    monkeypatch.setenv("DISABLE_REDIS", "true")
    body = {"error": "server_error", "error_description": "Internal AAD error"}
    client = _async_client(_async_response(500, body))

    with pytest.raises(GraphClientError) as exc_info:
        asyncio.run(
            exchange_for_graph_token(
                user_token="u-token",
                tenant_id="t-1",
                scopes=["https://graph.microsoft.com/User.Read.All"],
                email="alice@contoso.com",
                http_client=client,
                use_cache=False,
            )
        )

    err = exc_info.value
    assert not isinstance(err, InsufficientConsent)
    assert err.status_code == 500


def test_obo_success_returns_access_token(monkeypatch):
    monkeypatch.setenv("DISABLE_REDIS", "true")
    body = {"access_token": "graph-token-xyz", "expires_in": 3600}
    client = _async_client(_async_response(200, body))

    token = asyncio.run(
        exchange_for_graph_token(
            user_token="u-token",
            tenant_id="t-1",
            scopes=["https://graph.microsoft.com/User.Read.All"],
            email="alice@contoso.com",
            http_client=client,
            use_cache=False,
        )
    )

    assert token == "graph-token-xyz"
    client.post.assert_awaited_once()


def test_obo_missing_user_token_raises():
    with pytest.raises(GraphClientError):
        asyncio.run(
            exchange_for_graph_token(
                user_token="",
                tenant_id="t-1",
                scopes=["https://graph.microsoft.com/User.Read.All"],
                email="alice@contoso.com",
                http_client=None,
                use_cache=False,
            )
        )
