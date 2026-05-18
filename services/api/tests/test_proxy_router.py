"""Regression tests for proxy router upstream error handling."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from app import deps
from app.routers.proxy import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[deps.get_access_token] = lambda: "test-token"
    app.include_router(router)
    return app


def test_proxy_analytics_returns_504_on_upstream_timeout(monkeypatch):
    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, headers=None, content=None):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.routers.proxy.httpx.AsyncClient", TimeoutClient)
    client = TestClient(_make_app())

    response = client.get("/api/proxy/analytics/mission-control/encounters")

    assert response.status_code == 504
    assert "timed out" in response.json()["detail"].lower()


def test_proxy_analytics_forwards_delete_body(monkeypatch):
    """Regression: DELETE /episodes/{id} carries a JSON body
    (confirm_episode_id + reason). The proxy MUST forward that body,
    otherwise the upstream returns HTTP 422 'body: Field required'."""
    captured: dict = {}

    class CaptureClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            captured["content"] = content
            return httpx.Response(200, json={"success": True})

    monkeypatch.setattr("app.routers.proxy.httpx.AsyncClient", CaptureClient)
    client = TestClient(_make_app())

    payload = {"confirm_episode_id": "ep-123", "reason": "manual cleanup"}
    response = client.request(
        "DELETE", "/api/proxy/analytics/episodes/ep-123", json=payload
    )

    assert response.status_code == 200
    assert captured["method"] == "DELETE"
    assert captured["content"] is not None
    assert b"confirm_episode_id" in captured["content"]
    assert b"ep-123" in captured["content"]
    assert b"manual cleanup" in captured["content"]


def test_proxy_analytics_returns_502_on_upstream_connect_error(monkeypatch):
    class ConnectErrorClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, headers=None, content=None):
            req = httpx.Request("GET", "http://localhost:8003/analytics/test")
            raise httpx.ConnectError("connection failed", request=req)

    monkeypatch.setattr("app.routers.proxy.httpx.AsyncClient", ConnectErrorClient)
    client = TestClient(_make_app())

    response = client.get("/api/proxy/analytics/mission-control/encounters")

    assert response.status_code == 502
    assert "unavailable" in response.json()["detail"].lower()
