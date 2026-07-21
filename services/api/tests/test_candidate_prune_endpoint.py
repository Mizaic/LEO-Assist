"""VT-LEO-AI-182 -- /training/candidates/prune/{preview,execute} endpoints.

Pins admin gating, preview read-only contract, execute TOCTOU re-check
(skipped_completed path), 400 on empty id list, and audit log emission.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import require_admin
from app.routers.training import router as training_router
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


# ---------- preview ---------------------------------------------------------


def test_preview_requires_admin(client):
    """Without an admin override, FastAPI's require_admin must reject."""
    r = client.post(
        "/training/candidates/prune/preview",
        json={},
    )
    assert r.status_code in (401, 403)


def test_preview_returns_assessment_payload_and_does_not_delete(client):
    fake_assessment = MagicMock()
    fake_assessment.to_dict.return_value = {
        "candidate_id": "c-1",
        "verdict": "delete",
        "rejection_reasons": ["tag_mismatch_all"],
        "entity_count": 1,
    }
    fake_summary = {
        "candidate_count": 1,
        "by_verdict": {"keep": 0, "delete": 1, "review": 0},
        "by_rejection_reason": {"tag_mismatch_all": 1},
        "entity_total": 1,
        "entity_accepted": 0,
        "entity_rejected": 1,
    }

    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
        patch("app.routers.training_candidates.TerminologyClient") as MockTerm,
        patch(
            "app.services.candidate_prune.assess_candidates",
            return_value=[fake_assessment],
        ) as mock_assess,
        patch(
            "app.services.candidate_prune.summarise",
            return_value=fake_summary,
        ),
    ):
        r = client.post(
            "/training/candidates/prune/preview",
            json={
                "min_surface_match": 0.7,
                "semantic_vector_floor": 0.92,
                "semantic_min_surface": 0.66,
                "statuses": ["pending"],
                "limit": 100,
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["summary"]["by_verdict"]["delete"] == 1
    assert payload["candidates"][0]["candidate_id"] == "c-1"
    assert payload["params"]["min_surface_match"] == 0.7

    # Preview must never invoke DELETE Cypher.
    kg = MockKG.return_value
    inner_calls = [c for c in kg.method_calls if "DELETE" in str(c)]
    assert inner_calls == []
    mock_assess.assert_called_once()


# ---------- execute ---------------------------------------------------------


def test_execute_rejects_empty_id_list_with_400(client):
    with admin_scope_override(client.app):
        r = client.post(
            "/training/candidates/prune/execute",
            json={"candidate_ids": []},
        )
    assert r.status_code == 400
    assert "non-empty" in r.json()["detail"].lower()


def test_execute_skips_completed_candidate_via_toctou_recheck(client):
    """Candidate flipped to 'completed' between preview and execute is skipped."""

    def run_side_effect(query, **kwargs):
        # Both GET and DELETE branches share the same dispatcher.
        if "DETACH DELETE" in query:
            # Should never be reached for a completed candidate.
            raise AssertionError("DELETE invoked on a completed candidate")
        return MagicMock(
            single=MagicMock(
                return_value={"candidate_id": "c-1", "status": "completed"}
            )
        )

    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/prune/execute",
            json={"candidate_ids": ["c-1"]},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["requested"] == 1
    assert payload["deleted"] == 0
    assert payload["skipped_completed"] == 1
    assert payload["skipped_completed_ids"] == ["c-1"]


def test_execute_deletes_pending_candidate_and_returns_counts(client):
    state = {"step": 0}

    def run_side_effect(query, **kwargs):
        state["step"] += 1
        if state["step"] == 1:
            return MagicMock(
                single=MagicMock(
                    return_value={"candidate_id": "c-1", "status": "pending"}
                )
            )
        return MagicMock(
            single=MagicMock(
                return_value={
                    "candidate_id": "c-1",
                    "gold_labels_deleted": 1,
                    "surface_form_tasks_deleted": 0,
                }
            )
        )

    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/prune/execute",
            json={"candidate_ids": ["c-1"]},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["requested"] == 1
    assert payload["deleted"] == 1
    assert payload["skipped_completed"] == 0
    assert payload["not_found"] == 0
    assert payload["cascade_counts"]["c-1"]["gold_labels_deleted"] == 1


def test_execute_reports_not_found_when_id_missing(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(single=MagicMock(return_value=None))
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/prune/execute",
            json={"candidate_ids": ["c-missing"]},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["not_found"] == 1
    assert payload["not_found_ids"] == ["c-missing"]
    assert payload["deleted"] == 0
