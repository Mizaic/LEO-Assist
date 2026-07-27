"""Tests for services/api/app/routers/guidance_concepts.py."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import require_admin
from app.routers.guidance_concepts import router
from libs.auth.org_scope import CallerScope
from libs.llm_client.topic_expansion import TopicExpansionResult


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    def _admin() -> CallerScope:
        return CallerScope(email="admin@example.com", is_admin=True)

    app.dependency_overrides[require_admin] = _admin
    return TestClient(app)


def test_expand_topic_returns_terms():
    with patch(
        "app.routers.guidance_concepts.expand_topic_terms",
        return_value=TopicExpansionResult(
            terms=["cough", "fatigue"],
            reason="Common symptoms.",
            model_id="test",
        ),
    ) as mocked:
        res = _client().post(
            "/guidance/concepts/expand-topic",
            json={"phrase": "symptoms of lung cancer"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["terms"] == ["cough", "fatigue"]
    assert body["reason"] == "Common symptoms."
    mocked.assert_called_once()


def test_expand_topic_rejects_short_phrase():
    res = _client().post(
        "/guidance/concepts/expand-topic",
        json={"phrase": "x"},
    )
    assert res.status_code == 422
