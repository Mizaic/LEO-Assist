"""Tests for plan publish capability validation (M2.0a)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.fhir_api.app.routers.plan_definition import router

_app = FastAPI()
_app.include_router(router, prefix="/fhir")
client = TestClient(_app)


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_active_rejects_unregistered_capability(mock_cls) -> None:
    mc = MagicMock()
    mc.run.return_value = None
    mock_cls.return_value = mc

    resp = client.put(
        "/fhir/PlanDefinition/pd-test",
        json={
            "name": "Bad plan",
            "status": "active",
            "action": [{"id": "a1", "_subgraphId": "not_a_real_subgraph"}],
        },
    )
    assert resp.status_code == 422
    assert "not_a_real_subgraph" in resp.json()["detail"]


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_active_rejects_invalid_referral_policy(mock_cls) -> None:
    mc = MagicMock()
    mc.run.return_value = None
    mock_cls.return_value = mc

    resp = client.put(
        "/fhir/PlanDefinition/pd-referral-assessment",
        json={
            "name": "Referral plan",
            "status": "active",
            "_workflowMode": "durable_pubsub",
            "_referralPolicy": {
                "schemaVersion": "1.0",
                "extraction": {"windowSize": 3, "windowOverlap": 3},
            },
            "action": [{"id": "a1", "_subgraphId": "extraction"}],
        },
    )
    assert resp.status_code == 422
    assert "windowOverlap" in resp.json()["detail"]
