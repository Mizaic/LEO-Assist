"""VT-LEO-AI-193 -- POST /patients/.../coded-links/sync-from-gold.

Pins the dual-save contract used by the shared GoldLabelEditorDialog
on /care/* surfaces:

  - the request rejects 409 when live concept_ids drift from the
    client's expected baseline (optimistic concurrency)
  - desired entities with snomed_concept_id are upserted via
    PatientGraphWriter.upsert_documents_link
  - baseline concept_ids absent from the desired set are deleted via
    PatientGraphWriter.delete_documents_link
  - entities without snomed_concept_id are kept on the GoldLabel but
    skipped from live writes
  - the gold mirror (UPDATE_GOLD_LABEL_ENTITIES) runs after the live
    writes commit
  - 400 on empty label_id; 404 when the gold label cannot be located
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.patients import router as patients_router
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
    test_app.include_router(patients_router)
    return test_app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield c


# -- Mock helpers ------------------------------------------------------------


def _patient_session_for_sync(baseline_link_rows: list[dict[str, Any]]):
    """Mock PatientGraphClient where execute_write runs the supplied fn.

    Inside the tx we serve the LIST_ENCOUNTER_CODED_LINKS rows from
    ``baseline_link_rows`` so the optimistic concurrency check sees a
    stable baseline.
    """

    tx_calls: list[tuple[str, dict[str, Any]]] = []

    def tx_run(query, **kwargs):
        tx_calls.append((query, kwargs))
        if "OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)" in query:
            return iter(baseline_link_rows)
        # delete_documents_link expects a single() with `deleted` count.
        if "DELETE r" in query or "DELETE r," in query or "DELETE_CODED_LINK" in query:
            return MagicMock(single=MagicMock(return_value={"deleted": 1}))
        return MagicMock(single=MagicMock(return_value={"deleted": 1}))

    tx = MagicMock()
    tx.run.side_effect = tx_run

    inner = MagicMock()
    inner.execute_write.side_effect = lambda fn: fn(tx)

    pgc = MagicMock()
    pgc.session.return_value.__enter__ = lambda s: inner
    pgc.session.return_value.__exit__ = MagicMock(return_value=False)
    return pgc, tx_calls


def _kg_session_for_gold_mirror(label_present: bool = True):
    calls: list[tuple[str, dict[str, Any]]] = []

    def run_side_effect(query, **kwargs):
        calls.append((query, kwargs))
        # GET_GOLD_LABEL_BY_ID has no SET clause; UPDATE_GOLD_LABEL_ENTITIES does.
        is_get = (
            "MATCH (g:GoldLabel {label_id: $label_id})" in query
            and "SET g.entities_json" not in query
        )
        if is_get:
            if not label_present:
                return MagicMock(single=MagicMock(return_value=None))
            return MagicMock(
                single=MagicMock(
                    return_value={
                        "label_id": kwargs.get("label_id"),
                        "text": "deid",
                        "entities_json": "[]",
                        "source": "live_encounter_correction",
                    }
                )
            )
        return MagicMock(single=MagicMock(return_value=None))

    inner = MagicMock()
    inner.run.side_effect = run_side_effect

    kg = MagicMock()
    kg.session.return_value.__enter__ = lambda s: inner
    kg.session.return_value.__exit__ = MagicMock(return_value=False)
    return kg, calls


def _baseline_row(concept_id: str) -> dict[str, Any]:
    return {
        "encounter_id": "enc-1",
        "node_labels": ["Disease"],
        "concept_id": concept_id,
        "term": f"Term {concept_id}",
        "read_code": None,
        "semantic_tag": "disorder",
        "evidence": "",
        "evidence_sentence": "",
        "context": None,
        "modifiers": None,
        "body_site_concept_id": None,
        "body_site_term": None,
    }


# -- VT-193-TC-001 -- happy path: add + remove + update + gold mirror ----


def test_happy_path_adds_removes_and_mirrors_gold(client):
    """Baseline=[A,B], desired=[B,C] -> add C, remove A, update B,
    then mirror entities to the GoldLabel."""

    pgc, tx_calls = _patient_session_for_sync(
        [_baseline_row("A"), _baseline_row("B")]
    )
    kg, kg_calls = _kg_session_for_gold_mirror(label_present=True)

    desired_entities = [
        {
            "text": "term B",
            "label": "disorder",
            "semantic_tag": "disorder",
            "snomed_concept_id": "B",
            "snomed_term": "Term B",
            "assertion": "present",
        },
        {
            "text": "term C",
            "label": "disorder",
            "semantic_tag": "disorder",
            "snomed_concept_id": "C",
            "snomed_term": "Term C",
            "assertion": "present",
        },
    ]

    with (
        caller_scope_override(client.app),
        patch("app.routers.patients.PatientGraphClient", return_value=pgc),
        patch("app.routers.patients.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.patients.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/patients/pat-1/encounters/enc-1/coded-links/sync-from-gold",
            json={
                "label_id": "manual-1234",
                "expected_baseline_concept_ids": ["A", "B"],
                "entities": desired_entities,
            },
        )

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["gold_label_id"] == "manual-1234"
    assert payload["live_links_added"] == 1
    assert payload["live_links_removed"] == 1
    assert payload["live_links_updated"] == 1
    assert sorted(payload["baseline_concept_ids"]) == ["B", "C"]

    upsert_calls = [
        kwargs for q, kwargs in tx_calls
        if "MERGE (e)-[r:DOCUMENTS" in q
    ]
    upserted_ids = sorted(c["concept_id"] for c in upsert_calls)
    assert upserted_ids == ["B", "C"]

    delete_calls = [
        kwargs for q, kwargs in tx_calls
        if ("DELETE r" in q and "MATCH" in q and "concept_id" in q.lower())
    ]
    assert any(c.get("concept_id") == "A" for c in delete_calls), tx_calls

    mirror = [kwargs for q, kwargs in kg_calls if "SET g.entities_json" in q]
    assert len(mirror) == 1
    persisted = json.loads(mirror[0]["entities_json"])
    assert {ent["snomed_concept_id"] for ent in persisted} == {"B", "C"}


# -- VT-193-TC-002 -- optimistic concurrency: 409 on baseline drift ------


def test_baseline_drift_returns_409_and_no_writes(client):
    """Live shows [A,B,X] but client expected only [A,B] -> 409, no
    upsert/delete/mirror calls happen."""

    pgc, tx_calls = _patient_session_for_sync(
        [_baseline_row("A"), _baseline_row("B"), _baseline_row("X")]
    )
    kg, kg_calls = _kg_session_for_gold_mirror(label_present=True)

    with (
        caller_scope_override(client.app),
        patch("app.routers.patients.PatientGraphClient", return_value=pgc),
        patch("app.routers.patients.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.patients.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/patients/pat-1/encounters/enc-1/coded-links/sync-from-gold",
            json={
                "label_id": "manual-1234",
                "expected_baseline_concept_ids": ["A", "B"],
                "entities": [
                    {
                        "text": "term A",
                        "snomed_concept_id": "A",
                        "snomed_term": "Term A",
                        "semantic_tag": "disorder",
                        "assertion": "present",
                    }
                ],
            },
        )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "changed" in detail.lower() or "refresh" in detail.lower()
    upsert_calls = [q for q, _ in tx_calls if "MERGE (e)-[r:DOCUMENTS" in q]
    delete_calls = [q for q, _ in tx_calls if "DELETE r" in q]
    assert upsert_calls == []
    assert delete_calls == []
    mirror = [q for q, _ in kg_calls if "SET g.entities_json" in q]
    assert mirror == []


# -- VT-193-TC-003 -- empty entities removes all live links -------------


def test_empty_entities_removes_all_live_links(client):
    pgc, tx_calls = _patient_session_for_sync(
        [_baseline_row("A"), _baseline_row("B")]
    )
    kg, kg_calls = _kg_session_for_gold_mirror(label_present=True)

    with (
        caller_scope_override(client.app),
        patch("app.routers.patients.PatientGraphClient", return_value=pgc),
        patch("app.routers.patients.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.patients.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/patients/pat-1/encounters/enc-1/coded-links/sync-from-gold",
            json={
                "label_id": "manual-1234",
                "expected_baseline_concept_ids": ["A", "B"],
                "entities": [],
            },
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["live_links_added"] == 0
    assert payload["live_links_removed"] == 2
    assert payload["live_links_updated"] == 0
    assert payload["baseline_concept_ids"] == []
    mirror = [kwargs for q, kwargs in kg_calls if "SET g.entities_json" in q]
    assert json.loads(mirror[0]["entities_json"]) == []


# -- VT-193-TC-004 -- entities without concept_id only update gold ------


def test_entities_without_concept_id_only_update_gold(client):
    """An entity span the reviewer marked but did not link to SNOMED is
    kept in the gold label (so they can finish coding it later) but
    must not produce a live :DOCUMENTS write."""

    pgc, tx_calls = _patient_session_for_sync([])
    kg, kg_calls = _kg_session_for_gold_mirror(label_present=True)

    desired_entities = [
        {"text": "vague symptom", "label": "finding"},
    ]

    with (
        caller_scope_override(client.app),
        patch("app.routers.patients.PatientGraphClient", return_value=pgc),
        patch("app.routers.patients.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.patients.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/patients/pat-1/encounters/enc-1/coded-links/sync-from-gold",
            json={
                "label_id": "manual-1234",
                "expected_baseline_concept_ids": [],
                "entities": desired_entities,
            },
        )

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["live_links_added"] == 0
    assert payload["live_links_removed"] == 0
    assert payload["live_links_updated"] == 0
    assert payload["baseline_concept_ids"] == []

    upsert_calls = [q for q, _ in tx_calls if "MERGE (e)-[r:DOCUMENTS" in q]
    assert upsert_calls == []
    mirror = [kwargs for q, kwargs in kg_calls if "SET g.entities_json" in q]
    persisted = json.loads(mirror[0]["entities_json"])
    assert persisted == desired_entities


# -- VT-193-TC-005 -- empty label_id returns 400 -------------------------


def test_empty_label_id_returns_400(client):
    pgc, _ = _patient_session_for_sync([])
    kg, _ = _kg_session_for_gold_mirror(label_present=True)

    with (
        caller_scope_override(client.app),
        patch("app.routers.patients.PatientGraphClient", return_value=pgc),
        patch("app.routers.patients.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.patients.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/patients/pat-1/encounters/enc-1/coded-links/sync-from-gold",
            json={
                "label_id": "   ",
                "expected_baseline_concept_ids": [],
                "entities": [],
            },
        )

    assert r.status_code in (400, 422)


# -- VT-193-TC-006 -- missing gold label after live writes returns 404 --


def test_missing_gold_label_after_live_writes_returns_404(client):
    """If the live-side writes succeed but the GoldLabel cannot be
    located on the KG side we surface 404 so the dialog can prompt the
    reviewer instead of silently swallowing the error."""

    pgc, _ = _patient_session_for_sync([])
    kg, _ = _kg_session_for_gold_mirror(label_present=False)

    with (
        caller_scope_override(client.app),
        patch("app.routers.patients.PatientGraphClient", return_value=pgc),
        patch("app.routers.patients.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.patients.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/patients/pat-1/encounters/enc-1/coded-links/sync-from-gold",
            json={
                "label_id": "missing-label",
                "expected_baseline_concept_ids": [],
                "entities": [],
            },
        )

    assert r.status_code == 404
    assert "Gold label not found" in r.json()["detail"]


# -- VT-193-TC-007 -- assertion + body_site mapping pinned --------------


def test_payload_builder_maps_assertion_and_body_site(client):
    """Direct unit-style check on the helper used to build live
    SemanticLinkPayload objects from gold entities -- pins the field
    contract so the live :DOCUMENTS row carries the same assertion
    and body_site the dialog displayed."""

    from app.routers.patients import _build_link_payload_from_gold_entity

    payload = _build_link_payload_from_gold_entity(
        encounter_id="enc-1",
        entity={
            "text": "type 2 diabetes mellitus",
            "label": "disorder",
            "semantic_tag": "disorder",
            "snomed_concept_id": "73211009",
            "snomed_term": "Diabetes mellitus type 2",
            "assertion": "historical",
            "body_site_concept_id": "15776009",
            "body_site_term": "Pancreas",
        },
    )

    assert payload is not None
    assert payload.concept_id == "73211009"
    assert payload.term == "Diabetes mellitus type 2"
    assert payload.context["assertion"] == "historical"
    assert payload.context["historical"] is True
    assert payload.modifiers["body_site_concept_id"] == "15776009"
    assert payload.modifiers["body_site_term"] == "Pancreas"
    assert payload.source == "manual_gold_sync"

    # Empty concept_id -> None (gold-only entity).
    assert (
        _build_link_payload_from_gold_entity(
            encounter_id="enc-1",
            entity={"text": "x", "snomed_concept_id": ""},
        )
        is None
    )
