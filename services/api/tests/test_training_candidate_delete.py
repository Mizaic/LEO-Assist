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
from app.routers.training import router as training_router
from app.routers.training_candidates import (
    COUNT_TRAINING_CANDIDATES_PAGE,
    GET_TRAINING_CANDIDATE_BY_ID,
    GET_TRAINING_CANDIDATES_PAGE,
)
from app.routers.training_gold_labels import (
    GET_GOLD_LABEL_BY_CANDIDATE_ID,
    UPDATE_GOLD_LABEL_ENTITIES,
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
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
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
            MagicMock(),  # gold granularity metadata
            MagicMock(
                single=MagicMock(
                    return_value={
                        "label_id": "label-created",
                        "text": "example encounter text",
                        "entities_json": '[{"text":"example","label":"finding","semantic_tag":"finding"}]',
                        "quality_score": None,
                        "source": "manual_gold_draft",
                        "verified_by": "",
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
    assert payload["source"] == "manual_gold_draft"


def test_patch_gold_label_entities_persists_body_site_fields(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"label_id": "label-1"})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.patch(
            "/training/gold-labels/label-1/entities",
            json={
                "entities": [
                    {
                        "text": "burning sensation on micturition",
                        "label": "finding",
                        "assertion": "present",
                        "body_site": "bladder",
                        "body_site_concept_id": "89837001",
                        "body_site_term": "Urinary bladder structure",
                    }
                ]
            },
        )

    assert r.status_code == 200
    payload = r.json()
    saved_entity = payload["entities"][0]
    assert saved_entity["body_site"] == "bladder"
    assert saved_entity["body_site_concept_id"] == "89837001"
    assert saved_entity["body_site_term"] == "Urinary bladder structure"

    assert inner.run.call_count == 1
    query_arg = inner.run.call_args.args[0]
    params = inner.run.call_args.kwargs
    assert query_arg == UPDATE_GOLD_LABEL_ENTITIES
    assert '"body_site_concept_id": "89837001"' in params["entities_json"]
    assert '"body_site_term": "Urinary bladder structure"' in params["entities_json"]


def test_patch_gold_label_entities_persists_relations_and_mirrors_site(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"label_id": "label-1"})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.patch(
            "/training/gold-labels/label-1/entities",
            json={
                "entities": [
                    {
                        "text": "lump",
                        "label": "finding",
                        "assertion": "present",
                        "relations": [{"type": "finding_site", "target_idx": 1}],
                    },
                    {
                        "text": "right breast",
                        "label": "body_structure",
                        "snomed_concept_id": "76752008",
                        "snomed_term": "Right breast structure",
                    },
                ]
            },
        )

    assert r.status_code == 200
    entity = r.json()["entities"][0]
    assert entity["body_site"] == "right breast"
    assert entity["body_site_concept_id"] == "76752008"
    assert entity["body_site_term"] == "Right breast structure"
    assert entity["relations"][0]["type"] == "finding_site"
    assert entity["relations"][0]["target_idx"] == 1
    params = inner.run.call_args.kwargs
    assert '"relations"' in params["entities_json"]
    assert '"finding_site"' in params["entities_json"]


def test_patch_gold_label_entities_rejects_invalid_relation_policy(client):
    with admin_scope_override(client.app):
        r = client.patch(
            "/training/gold-labels/label-1/entities",
            json={
                "entities": [
                    {
                        "text": "metformin",
                        "label": "substance",
                        "relations": [{"type": "finding_site", "target_idx": 1}],
                    },
                    {"text": "left arm", "label": "body_structure"},
                ]
            },
        )
    assert r.status_code == 422
    assert "not allowed by relation policy" in r.json()["detail"].lower()


def test_patch_gold_label_entities_rejects_finding_to_finding_qualifies(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"label_id": "label-1"})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.patch(
            "/training/gold-labels/label-1/entities",
            json={
                "entities": [
                    {
                        "text": "increased in size",
                        "label": "finding",
                        "relations": [{"type": "qualifies", "target_idx": 1}],
                    },
                    {"text": "multiple lumps", "label": "finding"},
                ]
            },
        )

    assert r.status_code == 422
    assert "not allowed by relation policy" in r.json()["detail"]


def test_patch_gold_label_entities_allows_qualifier_value_qualifies_finding(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_gold_labels.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = MagicMock(
            single=MagicMock(return_value={"label_id": "label-1"})
        )
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.patch(
            "/training/gold-labels/label-1/entities",
            json={
                "entities": [
                    {
                        "text": "increased in size",
                        "label": "qualifier_value",
                        "relations": [{"type": "qualifies", "target_idx": 1}],
                    },
                    {"text": "multiple lumps", "label": "finding"},
                ]
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["entities"][0]["relations"][0]["type"] == "qualifies"
    assert payload["entities"][0]["relations"][0]["target_idx"] == 1


def test_mark_candidate_completed_returns_200_when_gold_exists(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
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
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
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
            json={
                "status": "completed",
                "max_candidates": 100,
                "similarity_threshold": 0.8,
            },
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
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
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
                return MagicMock(
                    single=MagicMock(return_value={"duplicates_marked": 1})
                )
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/dedupe/apply",
            json={
                "status": "completed",
                "max_candidates": 100,
                "similarity_threshold": 0.8,
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["duplicates_marked"] == 1
    assert payload["group_count"] == 1
    assert isinstance(payload["run_id"], str)


def test_candidate_dedupe_preview_detects_prefix_variant_duplicate(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-a",
                        "text": "Seen in fast track suspected breast cancer clinic",
                        "status": "completed",
                        "source": "pipeline_gold",
                        "updated_at": "2026-04-12T09:00:00Z",
                    },
                    {
                        "candidate_id": "cand-b",
                        "text": (
                            "Seen in 2WW Clinic?: Seen in fast track suspected "
                            "breast cancer clinic [DATE]"
                        ),
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
            json={
                "status": "completed",
                "max_candidates": 100,
                "similarity_threshold": 0.85,
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["group_count"] == 1
    assert payload["duplicate_count"] == 1


def test_candidate_dedupe_preview_accepts_lower_threshold(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-a",
                        "text": "suspected lung cancer clinic review",
                        "status": "completed",
                        "source": "pipeline_gold",
                        "updated_at": "2026-04-12T09:00:00Z",
                    },
                    {
                        "candidate_id": "cand-b",
                        "text": "suspected cancer clinic review",
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
            json={
                "status": "completed",
                "max_candidates": 100,
                "similarity_threshold": 0.5,
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["similarity_threshold"] == 0.5


def test_list_training_candidates_hydrates_missing_snomed_term(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
        patch("libs.terminology.preferred_terms._get_cache_client", return_value=None),
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-1",
                        "text": "example sentence",
                        "entities_json": '[{"text":"eschar","label":"finding","snomed_concept_id":"68640004"}]',
                        "source": "pipeline_gold",
                        "status": "pending",
                        "schema_version": "v4",
                        "created_at": "2026-04-12T10:00:00Z",
                        "updated_at": "2026-04-12T10:00:00Z",
                    }
                ]
            if query == COUNT_TRAINING_CANDIDATES_PAGE:
                return MagicMock(single=MagicMock(return_value={"total": 1}))
            if "UNWIND $ids AS cid" in query:
                return [{"concept_id": "68640004", "term": "Eschar (finding)"}]
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/training/candidates?page=1&page_size=20")

    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] == 1
    entities = payload["items"][0]["entities_json"]
    assert "Eschar" in entities


def test_find_similar_candidates_by_entity_returns_ranked_matches(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-source",
                        "text": "Urge incontinence discussed today",
                        "entities_json": '[{"text":"urge incontinence","label":"finding"}]',
                        "source": "pipeline_gold",
                        "status": "pending",
                        "updated_at": "2026-04-13T10:00:00Z",
                    },
                    {
                        "candidate_id": "cand-similar",
                        "text": "Patient reports urge incontinence symptoms",
                        "entities_json": '[{"text":"urge incontinence","label":"finding"}]',
                        "source": "pipeline_gold",
                        "status": "pending",
                        "updated_at": "2026-04-13T10:01:00Z",
                    },
                    {
                        "candidate_id": "cand-different",
                        "text": "Patient reports rash",
                        "entities_json": '[{"text":"rash","label":"finding"}]',
                        "source": "pipeline_gold",
                        "status": "pending",
                        "updated_at": "2026-04-13T10:02:00Z",
                    },
                ]
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/find-similar-by-entity",
            json={
                "candidate_id": "cand-source",
                "limit": 10,
                "similarity_threshold": 0.5,
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["source_candidate_id"] == "cand-source"
    assert payload["count"] == 1
    assert payload["items"][0]["candidate_id"] == "cand-similar"


def test_find_similar_candidates_by_entity_returns_404_for_missing_source(client):
    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()
        inner.run.return_value = []
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/find-similar-by-entity",
            json={"candidate_id": "missing-candidate"},
        )

    assert r.status_code == 404


def test_find_similar_candidates_by_entity_finds_source_with_non_pending_status(
    client,
):
    """Source candidate with status != 'pending' must not cause a 404."""
    from libs.cypher.training_candidate_queries import GET_TRAINING_CANDIDATES_PAGE

    with (
        admin_scope_override(client.app),
        patch("app.routers.training_candidates.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = MagicMock()

        def run_side_effect(query, **kwargs):
            if query == GET_TRAINING_CANDIDATES_PAGE:
                return [
                    {
                        "candidate_id": "cand-source",
                        "text": "Type 2 diabetes reviewed",
                        "entities_json": '[{"text":"type 2 diabetes","label":"finding"}]',
                        "source": "pipeline_gold",
                        "status": "completed",
                        "updated_at": "2026-04-15T10:00:00Z",
                    },
                    {
                        "candidate_id": "cand-pending",
                        "text": "Type 2 diabetes annual review",
                        "entities_json": '[{"text":"type 2 diabetes","label":"finding"}]',
                        "source": "pipeline_gold",
                        "status": "pending",
                        "updated_at": "2026-04-15T10:01:00Z",
                    },
                ]
            return MagicMock(single=MagicMock(return_value=None))

        inner.run.side_effect = run_side_effect
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.post(
            "/training/candidates/find-similar-by-entity",
            json={
                "candidate_id": "cand-source",
                "limit": 10,
                "similarity_threshold": 0.5,
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["source_candidate_id"] == "cand-source"
    assert payload["count"] == 1
    assert payload["items"][0]["candidate_id"] == "cand-pending"
