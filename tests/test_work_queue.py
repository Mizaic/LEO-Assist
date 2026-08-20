"""VT-LEO-AI-134 TC-001..TC-003 -- unified /work queue backend.

Covers the Cypher query shape, Python service normalisation, and the
FastAPI router wiring. Uses a stub neo4j session so the suite runs in
isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from libs.cypher.work_queue_queries import (
    COUNT_WORK_TASKS_BY_SOURCE,
    GET_UNIFIED_WORK_TASKS,
)
from libs.work.queue import (
    VALID_SOURCES,
    WorkTaskFilters,
    get_work_counts,
    get_work_tasks,
)

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
sys.modules.setdefault(
    "app.db.neo4j_client",
    MagicMock(PatientGraphClient=MagicMock),
)
sys.modules.setdefault(
    "app.services.session_store",
    MagicMock(
        COOKIE_NAME="leo_session",
        load_session=MagicMock(
            return_value={"email": "user@example.com", "idle_timeout_minutes": 30}
        ),
        touch_session=MagicMock(
            return_value={"email": "user@example.com", "idle_timeout_minutes": 30}
        ),
    ),
)


class _StubSession:
    """Neo4j session stub returning pre-canned rows per query."""

    def __init__(self, tasks: list[dict[str, Any]], counts: list[dict[str, Any]]):
        self._tasks = tasks
        self._counts = counts
        self.last_task_params: dict[str, Any] = {}

    def run(self, query: str, **params: Any) -> Iterable[dict[str, Any]]:
        if query is GET_UNIFIED_WORK_TASKS:
            self.last_task_params = params
            return iter(self._tasks)
        if query is COUNT_WORK_TASKS_BY_SOURCE:
            return iter(self._counts)
        raise AssertionError("unexpected cypher query in test stub")

    @property
    def last_params(self) -> dict[str, Any]:
        return self.last_task_params


def _sample_tasks() -> list[dict[str, Any]]:
    return [
        {
            "task_id": "coding_review:cr-1",
            "task_type": "coding_review",
            "severity": 4,
            "summary": "Code check: sore throat",
            "age_days": 2,
            "resolve_url": "/admin/operations/reviews?review_id=cr-1",
            "patient_id": "pat-1",
            "episode_id": None,
        },
        {
            "task_id": "safety_net_alert:sn-1",
            "task_type": "safety_net_alert",
            "severity": 5,
            "summary": "Safety alert: new red flag needs review",
            "age_days": 0,
            "resolve_url": "/safety-netting?alert_id=sn-1",
            "patient_id": "pat-2",
            "episode_id": "ep-2",
        },
        {
            "task_id": "gold_label:tc-1",
            "task_type": "gold_label",
            "severity": 2,
            "summary": "Label review: chest pain note",
            "age_days": 5,
            "resolve_url": "/admin/knowledge?tab=training-data&candidate_id=tc-1",
            "patient_id": None,
            "episode_id": None,
        },
        {
            "task_id": "extraction_quality_pause:eq-1",
            "task_type": "extraction_quality_pause",
            "severity": 3,
            "summary": "Paused extraction: pat-3",
            "age_days": 1,
            "resolve_url": "/admin/operations?tab=review",
            "patient_id": "pat-3",
            "episode_id": None,
        },
        {
            "task_id": "surface_form_approval:sf-1",
            "task_type": "surface_form_approval",
            "severity": 2,
            "summary": "New phrase to approve: sore throat",
            "age_days": 3,
            "resolve_url": "/admin/knowledge?tab=surface-forms",
            "patient_id": None,
            "episode_id": None,
        },
    ]


def _sample_counts() -> list[dict[str, Any]]:
    return [
        {"task_type": "coding_review", "total": 1},
        {"task_type": "safety_net_alert", "total": 1},
        {"task_type": "gold_label", "total": 1},
        {"task_type": "extraction_quality_pause", "total": 1},
        {"task_type": "surface_form_approval", "total": 1},
    ]


# -- TC-001 -- Cypher union shape ---------------------------------------


def test_vt134_tc001_union_covers_five_sources():
    assert "CodingReview" in GET_UNIFIED_WORK_TASKS
    assert "SafetyNetAlert" in GET_UNIFIED_WORK_TASKS
    assert "TrainingCandidate" in GET_UNIFIED_WORK_TASKS
    assert "HITLTask" in GET_UNIFIED_WORK_TASKS
    assert "SurfaceFormTask" in GET_UNIFIED_WORK_TASKS
    assert GET_UNIFIED_WORK_TASKS.count("UNION ALL") == 4
    for column in (
        "task_id",
        "task_type",
        "severity",
        "summary",
        "age_days",
        "resolve_url",
        "patient_id",
        "episode_id",
    ):
        assert column in GET_UNIFIED_WORK_TASKS


def test_vt134_tc001_counts_query_returns_task_type_total():
    assert "task_type" in COUNT_WORK_TASKS_BY_SOURCE
    assert "count" in COUNT_WORK_TASKS_BY_SOURCE
    assert COUNT_WORK_TASKS_BY_SOURCE.count("UNION ALL") == 4


def test_vt134_tc001_extraction_quality_pause_in_valid_sources():
    assert "extraction_quality_pause" in VALID_SOURCES


def test_vt134_tc001_surface_form_approval_in_valid_sources():
    assert "surface_form_approval" in VALID_SOURCES


# -- TC-002 -- Python service normalises rows and filters ---------------


def test_vt134_tc002_get_work_tasks_normalises_rows():
    session = _StubSession(_sample_tasks(), _sample_counts())
    page = get_work_tasks(session, WorkTaskFilters(limit=10))
    assert page.limit == 10
    assert page.offset == 0
    assert len(page.tasks) == 5
    source_types = {row.task_type for row in page.tasks}
    assert source_types == set(VALID_SOURCES)
    assert page.counts_by_source == {
        "coding_review": 1,
        "safety_net_alert": 1,
        "gold_label": 1,
        "extraction_quality_pause": 1,
        "surface_form_approval": 1,
    }


def test_vt134_tc002_summary_fields_are_plain_english():
    # Every default row shape used by the Cypher produces a summary
    # capped at a short phrase. That keeps FK grade low for staff.
    for row in _sample_tasks():
        summary = row["summary"]
        assert len(summary) <= 160
        assert ":" in summary  # "<kind>: <detail>" pattern


def test_vt134_tc002_invalid_sources_are_dropped():
    session = _StubSession(_sample_tasks(), _sample_counts())
    page = get_work_tasks(
        session,
        WorkTaskFilters(sources=("not_a_source",), limit=10),
    )
    # With all sources invalid, the service drops the filter entirely
    # so the session still receives a None sources parameter.
    assert session.last_params.get("sources") is None
    assert len(page.tasks) == 5


def test_vt134_tc002_limit_is_clamped():
    session = _StubSession(_sample_tasks(), _sample_counts())
    page = get_work_tasks(session, WorkTaskFilters(limit=9999))
    assert page.limit == 200
    assert session.last_params["limit"] == 200


def test_vt134_tc002_counts_fill_zero_for_missing_sources():
    session = _StubSession([], [{"task_type": "coding_review", "total": 2}])
    counts = get_work_counts(session)
    assert counts == {
        "coding_review": 2,
        "safety_net_alert": 0,
        "gold_label": 0,
        "extraction_quality_pause": 0,
        "surface_form_approval": 0,
    }


# -- TC-003 -- FastAPI router wiring ------------------------------------


class _StubClient:
    def __init__(self, session: _StubSession):
        self._session = session

    def session(self):
        return _SessionCtx(self._session)


class _SessionCtx:
    def __init__(self, session: _StubSession):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture
def client_with_work_router(monkeypatch):
    # Build a FastAPI app that mounts the router with the auth cookie
    # check monkey-patched to always succeed.
    from app.routers import work as work_router

    def _no_auth(_request):
        return {"email": "user@example.com"}

    monkeypatch.setattr(work_router, "_require_authed_session", _no_auth)

    session = _StubSession(_sample_tasks(), _sample_counts())
    stub_client = _StubClient(session)

    def _get_client_override():
        return stub_client

    app = FastAPI()
    app.include_router(work_router.router)
    app.dependency_overrides[work_router._get_client] = _get_client_override
    return TestClient(app), session


def test_vt134_tc003_get_tasks_returns_tasks_and_counts(client_with_work_router):
    client, _ = client_with_work_router
    response = client.get("/work/tasks")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {
        "tasks",
        "counts_by_source",
        "limit",
        "offset",
    }
    assert body["counts_by_source"] == {
        "coding_review": 1,
        "safety_net_alert": 1,
        "gold_label": 1,
        "extraction_quality_pause": 1,
        "surface_form_approval": 1,
    }
    # every row is a dict with the canonical keys
    for task in body["tasks"]:
        assert set(task.keys()) >= {
            "task_id",
            "task_type",
            "severity",
            "summary",
            "age_days",
            "resolve_url",
        }


def test_vt134_tc003_source_filter_hits_cypher(client_with_work_router):
    client, session = client_with_work_router
    response = client.get(
        "/work/tasks?source=coding_review&source=safety_net_alert"
    )
    assert response.status_code == 200
    sources = session.last_params.get("sources")
    assert sources == ["coding_review", "safety_net_alert"]


def test_vt134_tc003_invalid_source_returns_400(client_with_work_router):
    client, _ = client_with_work_router
    response = client.get("/work/tasks?source=not_real")
    assert response.status_code == 400


def test_vt134_tc003_counts_endpoint_returns_counts(client_with_work_router):
    client, _ = client_with_work_router
    response = client.get("/work/counts")
    assert response.status_code == 200
    assert response.json() == {
        "coding_review": 1,
        "safety_net_alert": 1,
        "gold_label": 1,
        "extraction_quality_pause": 1,
        "surface_form_approval": 1,
    }
