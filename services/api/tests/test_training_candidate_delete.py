"""Verification tests for training candidate delete endpoint.

VT-LEO-AI-096 - TrainingCandidate cascade delete in Knowledge Graph.
DI-LEO-AI-055 - GDPR-Isolated Learning Loop and Operations UX.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.training import (
    GET_GOLD_LABEL_BY_CANDIDATE_ID,
    GET_TRAINING_CANDIDATE_BY_ID,
    router as training_router,
)
from libs.cypher.training_candidate_queries import UPDATE_TRAINING_CANDIDATE_STATUS
from libs.auth.org_scope import CallerScope, get_caller_scope


@contextmanager
def admin_scope_override(app: FastAPI):
    scope = CallerScope(email="admin@example.com", is_admin=True, org_ids=[])
    app.dependency_overrides[get_caller_scope] = lambda: scope
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_caller_scope, None)


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


def test_delete_training_candidate_returns_200_and_counts(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(
                return_value={
                    "candidate_id": "cand-123",
                    "gold_labels_deleted": 2,
                    "surface_form_tasks_deleted": 1,
                }
            )
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.delete("/training/candidates/cand-123")

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_id"] == "cand-123"
    assert payload["gold_labels_deleted"] == 2
    assert payload["surface_form_tasks_deleted"] == 1


def test_delete_training_candidate_returns_404_when_missing(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value=None))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.delete("/training/candidates/missing-candidate")

    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_get_gold_label_by_candidate_returns_200(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(
                return_value={
                    "label_id": "label-1",
                    "text": "example",
                    "entities_json": "[]",
                    "quality_score": 1.0,
                    "source": "pipeline_gold",
                    "verified_by": "pipeline",
                    "verified_at": None,
                    "candidate_id": "cand-123",
                    "schema_version": "v4",
                    "created_at": None,
                    "updated_at": None,
                }
            )
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/training/gold-labels/by-candidate/cand-123")

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_id"] == "cand-123"
    assert payload["label_id"] == "label-1"


def test_get_gold_label_by_candidate_returns_404(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value=None))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/training/gold-labels/by-candidate/missing")

    assert r.status_code == 404
    assert "no goldlabel linked" in r.json()["detail"].lower()


def test_ensure_gold_label_by_candidate_returns_existing_label(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.side_effect = [
            MagicMock(
                single=MagicMock(
                    return_value={"candidate_id": "cand-123", "text": "example"}
                )
            ),
            MagicMock(
                single=MagicMock(
                    return_value={
                        "label_id": "label-existing",
                        "text": "example",
                        "entities_json": "[]",
                        "quality_score": 1.0,
                        "source": "pipeline_gold",
                        "verified_by": "pipeline",
                        "verified_at": None,
                        "candidate_id": "cand-123",
                        "schema_version": "v4",
                        "created_at": None,
                        "updated_at": None,
                    }
                )
            ),
        ]
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post("/training/gold-labels/by-candidate/cand-123/ensure")

    assert r.status_code == 200
    payload = r.json()
    assert payload["label_id"] == "label-existing"
    assert payload["candidate_id"] == "cand-123"


def test_ensure_gold_label_by_candidate_creates_when_missing(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.side_effect = [
            MagicMock(
                single=MagicMock(
                    return_value={
                        "candidate_id": "cand-123",
                        "text": "example encounter text",
                        "entities_json": '[{"text":"example","label":"finding","semantic_tag":"finding"}]',
                        "schema_version": "v4",
                    }
                )
            ),
            MagicMock(single=MagicMock(return_value=None)),
            MagicMock(),  # UPSERT_GOLD_LABEL
            MagicMock(
                single=MagicMock(
                    return_value={
                        "label_id": "label-created",
                        "text": "example encounter text",
                        "entities_json": '[{"text":"example","label":"finding","semantic_tag":"finding"}]',
                        "quality_score": None,
                        "source": "manual_gold_editor",
                        "verified_by": "admin@example.com",
                        "verified_at": None,
                        "candidate_id": "cand-123",
                        "schema_version": "v4",
                        "created_at": None,
                        "updated_at": None,
                    }
                )
            ),
        ]
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post("/training/gold-labels/by-candidate/cand-123/ensure")

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_id"] == "cand-123"
    assert payload["source"] == "manual_gold_editor"


def test_mark_candidate_completed_returns_200_when_gold_exists(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATE_BY_ID:
                return MagicMock(
                    single=MagicMock(return_value={"candidate_id": "cand-123"})
                )
            if query == GET_GOLD_LABEL_BY_CANDIDATE_ID:
                return MagicMock(single=MagicMock(return_value={"label_id": "label-1"}))
            if query == UPDATE_TRAINING_CANDIDATE_STATUS:
                return MagicMock(
                    single=MagicMock(
                        return_value={"candidate_id": "cand-123", "status": "completed"}
                    )
                )
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post("/training/candidates/cand-123/mark-completed")

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_id"] == "cand-123"
    assert payload["status"] == "completed"
    assert payload["gold_label_id"] == "label-1"


def test_mark_candidate_completed_returns_409_without_gold_label(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.side_effect = [
            MagicMock(single=MagicMock(return_value={"candidate_id": "cand-123"})),
            MagicMock(single=MagicMock(return_value=None)),
        ]
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post("/training/candidates/cand-123/mark-completed")

    assert r.status_code == 409
    assert "linked gold label exists" in r.json()["detail"].lower()
