"""VT-LEO-AI-191 -- POST /training/candidates/from-dry-run.

Pins the de-identification step before hashing, the candidate_id
contract (sha256 of de-identified text), entity re-anchoring with
unmappable drop, idempotency on second call, 400 on empty input,
and source_hint truncation.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.training import router as training_router
from libs.auth.org_scope import CallerScope, get_caller_scope


@contextmanager
def caller_scope_override(app: FastAPI):
    scope = CallerScope(email="curator@example.com", is_admin=True, org_ids=[])
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


def _kg_session_capture(run_lookup: dict[str, Any]):
    """Return a (MockKG, calls) pair that records every session.run call.

    `run_lookup` matches a query substring -> single() return value.
    """

    calls: list[tuple[str, dict[str, Any]]] = []

    def run_side_effect(query, **kwargs):
        calls.append((query, kwargs))
        for needle, single_value in run_lookup.items():
            if needle in query:
                return MagicMock(single=MagicMock(return_value=single_value))
        return MagicMock(single=MagicMock(return_value=None))

    inner = MagicMock()
    inner.run.side_effect = run_side_effect

    kg = MagicMock()
    kg.session.return_value.__enter__ = lambda s: inner
    kg.session.return_value.__exit__ = MagicMock(return_value=False)
    return kg, calls


# -- VT-191-TC-001 -- deidentify_text invoked before hashing ----------------


def test_deidentify_called_before_hash(client):
    raw = "Mr SMITH was reviewed by Dr Jones on 2026-04-18. NHS 123 456 7890."
    fake_deid = "Mr [PERSON] was reviewed by [PERSON] on [DATE]. NHS [NHS_NUMBER]."
    expected_id = hashlib.sha256(fake_deid.encode("utf-8")).hexdigest()

    kg, _calls = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch(
            "app.routers.training.deidentify_text",
            return_value=fake_deid,
        ) as mock_deid,
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
    ):
        r = client.post(
            "/training/candidates/from-dry-run",
            json={"encounter_text": raw, "entities": []},
        )

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["candidate_id"] == expected_id
    mock_deid.assert_called_once()
    args, kwargs = mock_deid.call_args
    assert args[0] == raw
    assert kwargs.get("ner") is True


# -- VT-191-TC-002 -- TrainingCandidate upsert source/status pinning --------


def test_upsert_uses_dry_run_correction_source_and_pending_status(client):
    deid = "patient reports cough and shortness of breath"

    kg, calls = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
    ):
        r = client.post(
            "/training/candidates/from-dry-run",
            json={
                "encounter_text": "raw text doesn't matter",
                "entities": [
                    {"text": "cough", "label": "OBSERVABLE_ENTITY"},
                ],
            },
        )

    assert r.status_code == 200
    upsert_calls = [
        kwargs for q, kwargs in calls if "MERGE (c:TrainingCandidate" in q
    ]
    assert len(upsert_calls) == 1
    upsert = upsert_calls[0]
    assert upsert["source"] == "dry_run_correction"
    assert upsert["status"] == "pending"
    assert upsert["schema_version"] == "v4"
    assert upsert["text"] == deid
    persisted = json.loads(upsert["entities_json"])
    assert persisted == [
        {
            "text": "cough",
            "label": "OBSERVABLE_ENTITY",
            "start": deid.index("cough"),
            "end": deid.index("cough") + len("cough"),
        }
    ]


# -- VT-191-TC-003 -- entity re-anchoring with unmappable drop --------------


def test_unmappable_entities_are_dropped_and_offsets_re_anchored(client):
    deid = "patient reports cough; [PERSON] noted no other symptoms"
    kg, calls = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
    ):
        r = client.post(
            "/training/candidates/from-dry-run",
            json={
                "encounter_text": "raw text",
                "entities": [
                    {"text": "cough", "label": "OBSERVABLE_ENTITY"},
                    {"text": "Dr Jones", "label": "PERSON"},
                ],
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["entity_count"] == 1
    assert payload["dropped_entity_count"] == 1

    upsert = next(kwargs for q, kwargs in calls if "MERGE (c:TrainingCandidate" in q)
    persisted = json.loads(upsert["entities_json"])
    assert len(persisted) == 1
    assert persisted[0]["text"] == "cough"
    assert deid[persisted[0]["start"] : persisted[0]["end"]] == "cough"


# -- VT-191-TC-004 -- second call is idempotent ------------------------------


def test_second_call_is_idempotent(client):
    deid = "patient reports cough"

    existing_candidate = {
        "candidate_id": hashlib.sha256(deid.encode()).hexdigest(),
        "text": deid,
        "entities_json": "[]",
        "source": "dry_run_correction",
        "status": "pending",
        "schema_version": "v4",
    }
    existing_label = {"label_id": "manual-existing-1234"}

    kg, calls = _kg_session_capture(
        {
            "MATCH (c:TrainingCandidate {candidate_id: $candidate_id})": (
                existing_candidate
            ),
            "MATCH (g:GoldLabel {candidate_id: $candidate_id})": existing_label,
        }
    )

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
    ):
        r = client.post(
            "/training/candidates/from-dry-run",
            json={"encounter_text": "anything", "entities": []},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_id"] == existing_candidate["candidate_id"]
    assert payload["label_id"] == existing_label["label_id"]
    upsert_candidate_calls = [
        q for q, _ in calls if "MERGE (c:TrainingCandidate" in q
    ]
    upsert_label_calls = [q for q, _ in calls if "MERGE (g:GoldLabel" in q]
    assert upsert_candidate_calls == []
    assert upsert_label_calls == []


# -- VT-191-TC-005 -- empty encounter_text returns 400 -----------------------


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_encounter_text_returns_400(client, text):
    with caller_scope_override(client.app):
        r = client.post(
            "/training/candidates/from-dry-run",
            json={"encounter_text": text, "entities": []},
        )
    assert r.status_code == 400
    assert "encounter_text" in r.json()["detail"]


# -- VT-191-TC-006 -- source_hint truncated to 64 chars ----------------------


def test_source_hint_is_truncated_to_64_chars(client):
    deid = "patient reports cough"
    long_hint = "x" * 200

    kg, calls = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
    ):
        r = client.post(
            "/training/candidates/from-dry-run",
            json={
                "encounter_text": "raw",
                "entities": [],
                "source_hint": long_hint,
            },
        )

    assert r.status_code == 200
    upsert = next(kwargs for q, kwargs in calls if "MERGE (c:TrainingCandidate" in q)
    assert upsert["hitl_reason"] is not None
    assert len(upsert["hitl_reason"]) <= 64
