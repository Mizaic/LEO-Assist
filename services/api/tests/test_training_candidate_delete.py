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

from app.deps import require_admin
from app.routers.training import (
    GET_GOLD_LABEL_BY_CANDIDATE_ID,
    GET_TRAINING_CANDIDATE_BY_ID,
    GET_TRAINING_CANDIDATES_PAGE,
    router as training_router,
)
from libs.cypher.training_candidate_queries import (
    MARK_TRAINING_CANDIDATE_DUPLICATES,
    UPDATE_TRAINING_CANDIDATE_STATUS,
)
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


def test_candidate_dedupe_preview_returns_groups(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-a",
                        "text": "fast track referral two week wait appointment",
                        "status": "completed",
                        "source": "pipeline_gold",
                        "updated_at": "2026-04-12T09:00:00Z",
                    },
                    {
                        "candidate_id": "cand-b",
                        "text": "two week wait fast track referral appointment",
                        "status": "completed",
                        "source": "pipeline_gold",
                        "updated_at": "2026-04-12T09:01:00Z",
                    },
                ]
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/dedupe/preview",
            json={"status": "completed", "max_candidates": 100, "similarity_threshold": 0.8},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_pool_size"] == 2
    assert payload["group_count"] == 1
    assert payload["duplicate_count"] == 1
    assert payload["groups"][0]["canonical"]["candidate_id"] in {"cand-a", "cand-b"}


def test_candidate_dedupe_apply_marks_duplicates(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-a",
                        "text": "fast track referral two week wait appointment",
                        "status": "completed",
                        "source": "pipeline_gold",
                        "updated_at": "2026-04-12T09:00:00Z",
                    },
                    {
                        "candidate_id": "cand-b",
                        "text": "two week wait fast track referral appointment",
                        "status": "completed",
                        "source": "pipeline_gold",
                        "updated_at": "2026-04-12T09:01:00Z",
                    },
                ]
            if query == MARK_TRAINING_CANDIDATE_DUPLICATES:
                return MagicMock(single=MagicMock(return_value={"duplicates_marked": 1}))
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/dedupe/apply",
            json={"status": "completed", "max_candidates": 100, "similarity_threshold": 0.8},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["duplicates_marked"] == 1
    assert payload["group_count"] == 1
    assert isinstance(payload["run_id"], str)
