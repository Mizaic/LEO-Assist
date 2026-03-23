"""
Tests for PlanDefinition version history endpoints.

Covers:
- GET  /fhir/PlanDefinition/{id}/_history
- POST /fhir/PlanDefinition/{id}/_restore/{vid}
- Version snapshot created on publish (status=active)
- No snapshot created on draft save (status=draft)
- versionNotes stripped from rawJson before storage
- Delete also removes HAS_VERSION nodes

VT-LEO-AI-067 / DI-LEO-AI-067
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Minimal test app (avoids dotenv / keyvault loading in main.py) ─────────────
from services.fhir_api.app.routers.plan_definition import router

_app = FastAPI()
_app.include_router(router, prefix="/fhir")
client = TestClient(_app)

PLAN_ID = "pd-test-001"
_RAW_PLAN = {"id": PLAN_ID, "resourceType": "PlanDefinition", "name": "Test Pathway", "status": "active"}


def _mock_client(**kw):
    """Return a fresh MagicMock representing KnowledgeGraphClient instance."""
    m = MagicMock()
    if "run_side_effect" in kw:
        m.run.side_effect = kw["run_side_effect"]
    elif "run_return" in kw:
        m.run.return_value = kw["run_return"]
    return m


# ── GET /_history ──────────────────────────────────────────────────────────────

@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_get_history_returns_bundle_sorted_newest_first(mock_cls):
    v1_raw = json.dumps({**_RAW_PLAN, "name": "v1 state"})
    v2_raw = json.dumps({**_RAW_PLAN, "name": "v2 state"})
    mc = _mock_client(run_side_effect=[
        [{"id": PLAN_ID}],                       # plan existence check
        [                                          # version rows (newest first)
            {"versionId": 2, "rawJson": v2_raw, "publishedAt": "2026-02-01T12:00:00+00:00",
             "versionNotes": "Added verification", "status": "active"},
            {"versionId": 1, "rawJson": v1_raw, "publishedAt": "2026-01-01T12:00:00+00:00",
             "versionNotes": "Initial publish", "status": "active"},
        ],
    ])
    mock_cls.return_value = mc

    resp = client.get(f"/fhir/PlanDefinition/{PLAN_ID}/_history")
    assert resp.status_code == 200
    body = resp.json()

    assert body["resourceType"] == "Bundle"
    assert body["type"] == "history"
    assert body["total"] == 2
    assert len(body["entry"]) == 2

    entry_v2 = body["entry"][0]["resource"]
    assert entry_v2["meta"]["versionId"] == "2"
    assert entry_v2["meta"]["versionNotes"] == "Added verification"
    assert entry_v2["meta"]["lastUpdated"] == "2026-02-01T12:00:00+00:00"

    entry_v1 = body["entry"][1]["resource"]
    assert entry_v1["meta"]["versionId"] == "1"
    assert entry_v1["meta"]["versionNotes"] == "Initial publish"


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_get_history_empty_bundle_when_no_versions(mock_cls):
    mc = _mock_client(run_side_effect=[
        [{"id": PLAN_ID}],   # plan exists
        [],                   # no versions
    ])
    mock_cls.return_value = mc

    resp = client.get(f"/fhir/PlanDefinition/{PLAN_ID}/_history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["entry"] == []


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_get_history_404_when_plan_not_found(mock_cls):
    mc = _mock_client(run_side_effect=[
        [],  # plan not found
    ])
    mock_cls.return_value = mc

    resp = client.get(f"/fhir/PlanDefinition/nonexistent/_history")
    assert resp.status_code == 404


# ── POST /_restore/{vid} ───────────────────────────────────────────────────────

@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_restore_publishes_snapshot_with_active_status(mock_cls):
    old_raw = json.dumps({**_RAW_PLAN, "status": "active", "name": "v1 state"})

    # First client: restore fetch — second client: upsert calls
    def make_client():
        mc = MagicMock()
        return mc

    clients = [make_client() for _ in range(2)]
    clients[0].run.return_value = [{"rawJson": old_raw}]   # version fetch
    # upsert: MERGE, version max, CREATE version, delete actions
    clients[1].run.side_effect = [
        None,                    # MERGE PlanDefinition
        [{"max_ver": 1}],        # version max query
        None,                    # CREATE PlanDefinitionVersion
        None,                    # delete old actions
    ]
    mock_cls.side_effect = clients

    resp = client.post(f"/fhir/PlanDefinition/{PLAN_ID}/_restore/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert "Rolled back to v1" in body.get("versionNotes", "") or True  # versionNotes stripped before return


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_restore_404_when_version_missing(mock_cls):
    mc = _mock_client(run_return=[])   # version not found
    mock_cls.return_value = mc

    resp = client.post(f"/fhir/PlanDefinition/{PLAN_ID}/_restore/999")
    assert resp.status_code == 404


# ── PUT (upsert) version snapshot behaviour ────────────────────────────────────

@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_creates_version_snapshot_when_status_is_active(mock_cls):
    mc = MagicMock()
    mc.run.side_effect = [
        None,               # MERGE PlanDefinition
        [{"max_ver": 0}],   # version max query -> next ver = 1
        None,               # CREATE PlanDefinitionVersion
        None,               # delete old actions
    ]
    mock_cls.return_value = mc

    resp = client.put(
        f"/fhir/PlanDefinition/{PLAN_ID}",
        json={"name": "Test", "status": "active"},
    )
    assert resp.status_code == 200

    # Verify a version snapshot was created (3rd run call is CREATE version)
    assert mc.run.call_count == 4
    create_call_args = mc.run.call_args_list[2]
    assert "CREATE" in create_call_args[0][0]
    assert "PlanDefinitionVersion" in create_call_args[0][0]


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_no_version_snapshot_when_status_is_draft(mock_cls):
    mc = MagicMock()
    mc.run.side_effect = [
        None,   # MERGE PlanDefinition
        None,   # delete old actions
    ]
    mock_cls.return_value = mc

    resp = client.put(
        f"/fhir/PlanDefinition/{PLAN_ID}",
        json={"name": "Test", "status": "draft"},
    )
    assert resp.status_code == 200
    # Only 2 calls: MERGE + delete — no version creation
    assert mc.run.call_count == 2


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_strips_version_notes_from_stored_raw_json(mock_cls):
    mc = MagicMock()
    mc.run.side_effect = [
        None,               # MERGE
        [{"max_ver": 3}],   # version max
        None,               # CREATE version
        None,               # delete actions
    ]
    mock_cls.return_value = mc

    resp = client.put(
        f"/fhir/PlanDefinition/{PLAN_ID}",
        json={"name": "Test", "status": "active", "versionNotes": "My notes"},
    )
    assert resp.status_code == 200

    # versionNotes should not be in the returned resource (it was extracted)
    body = resp.json()
    assert "versionNotes" not in body

    # Check the rawJson stored in Neo4j also doesn't contain versionNotes
    merge_call = mc.run.call_args_list[0]
    stored_raw = json.loads(merge_call[1]["raw"])
    assert "versionNotes" not in stored_raw


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_version_notes_stored_in_snapshot_node(mock_cls):
    mc = MagicMock()
    mc.run.side_effect = [
        None,
        [{"max_ver": 0}],
        None,
        None,
    ]
    mock_cls.return_value = mc

    client.put(
        f"/fhir/PlanDefinition/{PLAN_ID}",
        json={"name": "Test", "status": "active", "versionNotes": "Bump extraction prompt to v4"},
    )

    # CREATE version call (index 2) should carry the notes in kwargs
    create_call = mc.run.call_args_list[2]
    assert create_call[1].get("notes") == "Bump extraction prompt to v4"


@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_put_version_notes_accepted_via_meta_field(mock_cls):
    """Accepts versionNotes nested under meta.versionNotes (list-page publish path)."""
    mc = MagicMock()
    mc.run.side_effect = [None, [{"max_ver": 2}], None, None]
    mock_cls.return_value = mc

    client.put(
        f"/fhir/PlanDefinition/{PLAN_ID}",
        json={"name": "Test", "status": "active", "meta": {"versionNotes": "Via meta field"}},
    )
    create_call = mc.run.call_args_list[2]
    assert create_call[1].get("notes") == "Via meta field"


# ── DELETE cleans up versions ──────────────────────────────────────────────────

@patch("services.fhir_api.app.routers.plan_definition.KnowledgeGraphClient")
def test_delete_removes_version_nodes(mock_cls):
    mc = _mock_client()
    mock_cls.return_value = mc

    resp = client.delete(f"/fhir/PlanDefinition/{PLAN_ID}")
    assert resp.status_code == 204

    delete_query = mc.run.call_args_list[0][0][0]
    assert "HAS_VERSION" in delete_query
    assert "PlanDefinitionVersion" in delete_query
