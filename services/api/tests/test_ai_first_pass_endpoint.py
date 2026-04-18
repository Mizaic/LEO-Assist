"""VT-LEO-AI-200 -- /training/candidates/ai-first-pass/jobs endpoints.

Cases:
  TC-013: POST /jobs requires admin (403 without override).
  TC-014: POST /jobs returns run_id and queues a worker.
  TC-015: GET /jobs/{run_id} returns final summary after completion.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import require_admin
from app.routers.training import router as training_router
from app.services.candidate_ai_first_pass._job_runner import reset_for_tests
from libs.auth.org_scope import CallerScope, get_caller_scope


@contextmanager
def admin_scope_override(app: FastAPI):
    scope = CallerScope(email="admin@example.com", is_admin=True, org_ids=[])
    app.dependency_overrides[get_caller_scope] = lambda: scope
    app.dependency_overrides[require_admin] = lambda: scope
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_caller_scope, None)
        app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def _clean_jobs():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(training_router)
    return test_app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield c


def test_VT_194_TC_013_post_jobs_requires_admin(client):
    r = client.post("/training/candidates/ai-first-pass/jobs", json={})
    assert r.status_code in (401, 403)


def test_VT_194_TC_014_post_jobs_returns_run_id(client):
    with admin_scope_override(client.app), patch(
        "app.routers._training_ai_first_pass.create_job"
    ) as mock_create, patch.dict(
        "sys.modules",
        {"libs.neo4j_client.client": MagicMock()},
    ):
        state = MagicMock()
        state.run_id = "run-test-123"
        state.status = "running"
        state.params = {"limit": 10}
        mock_create.return_value = state

        r = client.post(
            "/training/candidates/ai-first-pass/jobs",
            json={"limit": 10, "max_workers": 2, "dry_run": True},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "run-test-123"
    assert body["status"] == "running"
    assert mock_create.called
    kwargs = mock_create.call_args.kwargs
    assert kwargs["params"].limit == 10
    assert kwargs["params"].dry_run is True
    assert kwargs["run_in_background"] is True


def test_VT_194_TC_015_get_job_returns_summary_after_completion(client):
    with admin_scope_override(client.app), patch(
        "app.routers._training_ai_first_pass.get_job"
    ) as mock_get:
        state = MagicMock()
        state.to_dict.return_value = {
            "run_id": "run-done",
            "status": "completed",
            "started_at": "2026-04-17T20:00:00Z",
            "finished_at": "2026-04-17T20:05:00Z",
            "candidate_count": 3,
            "summary": {
                "candidate_count": 3,
                "by_verdict": {"pre_done": 2, "delete": 1, "review": 0},
                "by_action": {"upserted_pre_done": 2, "deleted": 1},
                "errors": 0,
            },
            "params": {},
            "sample_outcomes": [],
            "error": None,
        }
        mock_get.return_value = state

        r = client.get("/training/candidates/ai-first-pass/jobs/run-done")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["summary"]["by_verdict"]["pre_done"] == 2
    assert body["summary"]["by_action"]["deleted"] == 1


def test_get_job_returns_404_for_unknown_run_id(client):
    with admin_scope_override(client.app), patch(
        "app.routers._training_ai_first_pass.get_job", return_value=None
    ):
        r = client.get("/training/candidates/ai-first-pass/jobs/missing-run")
    assert r.status_code == 404


def test_events_endpoint_returns_404_for_unknown_run_id(client):
    with admin_scope_override(client.app), patch(
        "app.routers._training_ai_first_pass.get_job", return_value=None
    ):
        r = client.get(
            "/training/candidates/ai-first-pass/jobs/missing-run/events"
        )
    assert r.status_code == 404
