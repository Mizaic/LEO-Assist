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
