"""Tests for mail Graph credential wiring in services/api/app/services/mail.py."""

from __future__ import annotations

import importlib

import httpx
import pytest


@pytest.fixture
def mail_module(monkeypatch):
    monkeypatch.setenv("MAIL_GRAPH_TENANT_ID", "corp-tenant-guid")
    monkeypatch.setenv("MAIL_GRAPH_CLIENT_ID", "mail-app-client-id")
    monkeypatch.setenv("MAIL_GRAPH_CLIENT_SECRET", "mail-app-secret")
    monkeypatch.setenv("MAIL_FROM_ADDRESS", "leo.support@mizaic.com")
    import app.services.mail as mod

    importlib.reload(mod)
    return mod


def test_mail_graph_token_url_uses_mail_tenant(mail_module):
    assert (
        mail_module._mail_graph_token_url()
        == "https://login.microsoftonline.com/corp-tenant-guid/oauth2/v2.0/token"
    )


def test_get_graph_token_uses_mail_graph_credentials(mail_module, monkeypatch):
    captured: dict = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"access_token": "tok"})

    monkeypatch.setattr(mail_module.httpx, "post", fake_post)
    token = mail_module._get_graph_token()
    assert token == "tok"
    assert captured["url"].endswith("/corp-tenant-guid/oauth2/v2.0/token")
    assert captured["data"]["client_id"] == "mail-app-client-id"
    assert captured["data"]["client_secret"] == "mail-app-secret"


def test_get_graph_token_requires_mail_graph_config(monkeypatch):
    monkeypatch.delenv("MAIL_GRAPH_TENANT_ID", raising=False)
    monkeypatch.setenv("MAIL_GRAPH_CLIENT_ID", "x")
    monkeypatch.setenv("MAIL_GRAPH_CLIENT_SECRET", "y")
    import app.services.mail as mod

    importlib.reload(mod)
    with pytest.raises(RuntimeError, match="MAIL_GRAPH_TENANT_ID"):
        mod._get_graph_token()
