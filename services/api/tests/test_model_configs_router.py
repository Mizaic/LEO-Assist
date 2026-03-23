"""Verification tests for the model-configs router create and delete endpoints.

VT-LEO-AI-069 — ModelConfig Create and Delete Router Verification
DI-LEO-AI-069 — ModelConfig Create and Delete via Admin API
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from libs.auth.org_scope import CallerScope, get_caller_scope


@contextmanager
def admin_scope_override():
    scope = CallerScope(email="admin@example.com", is_admin=True, org_ids=[])
    app.dependency_overrides[get_caller_scope] = lambda: scope
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_caller_scope, None)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield c


# ---------------------------------------------------------------------------
# VT-069-001: POST /model-configs — creates and returns 201
# ---------------------------------------------------------------------------

def test_post_model_config_creates_and_returns_201(client):
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        # GET_MODEL_CONFIG returns None (no existing node)
        inner.run.return_value = MagicMock(single=MagicMock(return_value=None))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post("/model-configs", json={
            "key": "aws:small",
            "provider": "aws",
            "tier": "small",
            "displayName": "Claude Haiku (AWS)",
            "modelId": "eu.anthropic.claude-haiku-4-5",
            "costPer1mInput": 1.1,
            "costPer1mCachedInput": 0.11,
            "costPer1mOutput": 5.5,
            "isActive": True,
        })

    assert r.status_code == 201
    data = r.json()
    assert data["key"] == "aws:small"
    assert data["status"] == "created"


# ---------------------------------------------------------------------------
# VT-069-002: POST /model-configs — duplicate key returns 409
# ---------------------------------------------------------------------------

def test_post_model_config_duplicate_key_returns_409(client):
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        # GET_MODEL_CONFIG returns an existing row
        inner.run.return_value = MagicMock(single=MagicMock(return_value={"key": "aws:small"}))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post("/model-configs", json={
            "key": "aws:small",
            "provider": "aws",
            "tier": "small",
            "displayName": "Claude Haiku",
            "modelId": "test",
        })

    assert r.status_code == 409


# ---------------------------------------------------------------------------
# VT-069-003: POST /model-configs — missing required field returns 422
# ---------------------------------------------------------------------------

def test_post_model_config_missing_key_returns_422(client):
    with admin_scope_override():
        r = client.post("/model-configs", json={
            "provider": "aws",
            "tier": "small",
            "displayName": "Missing key field",
        })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# VT-069-004: DELETE /model-configs/{key} — removes existing node and returns 200
# ---------------------------------------------------------------------------

def test_delete_model_config_returns_200(client):
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value={"deleted": 1}))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.delete("/model-configs/aws:small")

    assert r.status_code == 200
    assert r.json()["status"] == "deleted"


# ---------------------------------------------------------------------------
# VT-069-005: DELETE /model-configs/{key} — 404 for non-existent key
# ---------------------------------------------------------------------------

def test_delete_model_config_not_found_returns_404(client):
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value={"deleted": 0}))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.delete("/model-configs/azure:max")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# VT-069-006: GET /model-configs — list returns correctly
# ---------------------------------------------------------------------------

def test_get_model_configs_returns_list(client):
    rows = [
        {"key": "aws:small", "provider": "aws", "tier": "small", "displayName": "Haiku",
         "modelId": "haiku-id", "costPer1mInput": 1.1, "costPer1mCachedInput": 0.11,
         "costPer1mOutput": 5.5, "isActive": True, "source": "seed", "updatedAt": ""},
        {"key": "azure:big", "provider": "azure", "tier": "big", "displayName": "GPT-5",
         "modelId": "gpt-5", "costPer1mInput": 1.375, "costPer1mCachedInput": 0.138,
         "costPer1mOutput": 11.0, "isActive": True, "source": "user", "updatedAt": ""},
    ]
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(data=MagicMock(return_value=rows))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/model-configs")

    assert r.status_code == 200
    assert len(r.json()["modelConfigs"]) == 2


def test_get_service_config_returns_config(client):
    row = {
        "key": "terminology:resolve_runtime",
        "category": "terminology",
        "displayName": "Terminology resolve runtime",
        "description": "Runtime controls",
        "configJson": '{"timeout_seconds": 45, "max_concurrent_requests": 2}',
        "source": "seed",
        "updatedAt": "",
    }
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value=row))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/service-configs/terminology:resolve_runtime")

    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "terminology:resolve_runtime"
    assert body["config"]["timeout_seconds"] == 45


def test_put_service_config_upserts(client):
    with (
        admin_scope_override(),
        patch("app.routers.model_configs.CodingGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value={"key": "terminology:resolve_runtime"}))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.put("/service-configs/terminology:resolve_runtime", json={
            "category": "terminology",
            "displayName": "Terminology resolve runtime",
            "description": "Runtime controls",
            "config": {
                "timeout_seconds": 45,
                "max_retries": 3,
                "cooldown_seconds": 60,
                "final_attempts": 1,
                "max_concurrent_requests": 2,
                "max_terms_per_request": 8,
            },
        })

    assert r.status_code == 200
    assert r.json()["status"] == "updated"
