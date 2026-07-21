"""Verification tests for the LLM spend analytics router.

VT-LEO-AI-069 -- ModelConfig Create and Delete Router Verification (shared
DI/VT family; these two tests moved out of test_model_configs_router.py
when /analytics/llm-spend/* moved to app/routers/llm_usage.py, 2026-07
CTO peer-review item 2: core-api router decomposition -- pure move, no
behaviour change).
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


@contextmanager
def scoped_override(*, is_admin: bool, org_ids: list[str]):
    scope = CallerScope(email="user@example.com", is_admin=is_admin, org_ids=org_ids)
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


def test_run_llm_spend_applies_selected_org_filter_for_admin(client):
    with (
        admin_scope_override(),
        patch("app.routers.llm_usage.PatientGraphClient") as MockPG,
    ):
        pg = MockPG.return_value
        inner = MagicMock()
        rows = [
            {
                "runId": "run-1",
                "patientId": "p-1",
                "encounterId": "e-1",
                "status": "completed",
                "durationMs": 10,
                "inputTokens": 100,
                "outputTokens": 50,
                "cachedTokens": 20,
                "costUsd": 0.0123,
                "createdAt": "2026-04-11T00:00:00Z",
            }
        ]
        totals = [
            {
                "runCount": 1,
                "inputTokens": 100,
                "outputTokens": 50,
                "cachedTokens": 20,
                "costUsd": 0.0123,
            }
        ]
        inner.run.side_effect = [
            MagicMock(data=MagicMock(return_value=rows)),
            MagicMock(data=MagicMock(return_value=totals)),
        ]
        pg.session.return_value.__enter__ = lambda s: inner
        pg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get(
            "/analytics/llm-spend/runs?org_id=org-123&from=2026-04-01T00:00:00Z&to=2026-04-11T23:59:59Z"
        )

    assert r.status_code == 200
    assert r.json()["totals"]["runCount"] == 1
    first_call_kwargs = inner.run.call_args_list[0].kwargs
    assert first_call_kwargs["selected_org_id"] == "org-123"
    assert first_call_kwargs["from_date"] == "2026-04-01T00:00:00Z"
    assert first_call_kwargs["to_date"] == "2026-04-11T23:59:59Z"


def test_run_llm_spend_rejects_org_outside_non_admin_scope(client):
    with scoped_override(is_admin=False, org_ids=["org-allowed"]):
        r = client.get("/analytics/llm-spend/runs?org_id=org-denied")

    assert r.status_code == 403
