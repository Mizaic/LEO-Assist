"""VT-LEO-AI-211 -- POST /training/gold-labels/from-encounter.

Pins the live-encounter -> draft-GoldLabel seeding contract:

  - encounter text is de-identified server-side (PHI never leaves
    Neo4j or enters the gold dataset)
  - candidate_id is sha256 of the de-identified text (idempotent)
  - live :DOCUMENTS edges are mapped onto the gold entity shape
    consumed by the editor dialog (snomed_concept_id, snomed_term,
    semantic_tag, assertion, body_site_*)
  - links whose evidence cannot be re-anchored after de-id are
    dropped and counted in `dropped_link_count`
  - the response carries the canonical baseline_concept_ids that the
    sync-from-gold endpoint uses for optimistic concurrency
  - 404 when the encounter is missing; 400 on empty text/payload
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


# -- Mock helpers ------------------------------------------------------------


def _patient_session_with(encounter_row: dict[str, Any] | None, link_rows: list[dict[str, Any]]):
    """Return a (PatientGraphClient mock, recorded calls) pair.

    The mock returns ``encounter_row`` for GET_ENCOUNTER lookups and
    iterates ``link_rows`` for LIST_ENCOUNTER_CODED_LINKS lookups.
    """

    calls: list[tuple[str, dict[str, Any]]] = []

    def run_side_effect(query, **kwargs):
        calls.append((query, kwargs))
        if "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)" in query and (
            "OPTIONAL MATCH (e)-[r:DOCUMENTS]->()" in query
        ):
            return MagicMock(single=MagicMock(return_value=encounter_row))
        if "OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)" in query:
            return iter(link_rows)
        return MagicMock(single=MagicMock(return_value=None))

    inner = MagicMock()
    inner.run.side_effect = run_side_effect

    pgc = MagicMock()
    pgc.session.return_value.__enter__ = lambda s: inner
    pgc.session.return_value.__exit__ = MagicMock(return_value=False)
    return pgc, calls


def _kg_session_capture(run_lookup: dict[str, Any]):
    """Mimics the Knowledge graph session pattern used elsewhere.

    Includes a fallback synthetic GoldLabel row for GET_GOLD_LABEL_BY_ID
    so the response payload is always populated.
    """

    calls: list[tuple[str, dict[str, Any]]] = []

    def run_side_effect(query, **kwargs):
        calls.append((query, kwargs))
        for needle, single_value in run_lookup.items():
            if needle in query:
                return MagicMock(single=MagicMock(return_value=single_value))
        if "MATCH (g:GoldLabel {label_id: $label_id})" in query:
            label_id = kwargs.get("label_id", "manual-stub")
            synth = {
                "label_id": label_id,
                "text": "",
                "entities_json": "[]",
                "quality_score": None,
                "source": "live_encounter_correction",
                "verified_by": "",
                "verified_at": None,
                "candidate_id": kwargs.get("candidate_id"),
                "schema_version": "v4",
                "created_at": None,
                "updated_at": None,
            }
            return MagicMock(single=MagicMock(return_value=synth))
        return MagicMock(single=MagicMock(return_value=None))

    inner = MagicMock()
    inner.run.side_effect = run_side_effect

    kg = MagicMock()
    kg.session.return_value.__enter__ = lambda s: inner
    kg.session.return_value.__exit__ = MagicMock(return_value=False)
    return kg, calls


def _patch_targets():
    """Standard set of patches used by every happy-path test below."""

    return [
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ]


# -- VT-192-TC-001 -- happy path: live links mapped to gold entities -----


def test_happy_path_maps_live_links_to_gold_entities(client):
    raw = "Mr SMITH attended on 2026-04-18 with type 2 diabetes mellitus and asthma."
    deid = "patient attended with type 2 diabetes mellitus and asthma"

    encounter_row = {
        "encounter_id": "enc-1",
        "date": "2026-04-18",
        "text": raw,
        "coded_count": 2,
    }
    link_rows = [
        {
            "encounter_id": "enc-1",
            "node_labels": ["Disease"],
            "concept_id": "73211009",
            "term": "Diabetes mellitus type 2",
            "read_code": None,
            "semantic_tag": "disorder",
            "evidence": "type 2 diabetes mellitus",
            "evidence_sentence": "type 2 diabetes mellitus",
            "context": json.dumps({"assertion": "present"}),
            "modifiers": None,
            "body_site_concept_id": None,
            "body_site_term": None,
        },
        {
            "encounter_id": "enc-1",
            "node_labels": ["Disease"],
            "concept_id": "195967001",
            "term": "Asthma",
            "read_code": None,
            "semantic_tag": "disorder",
            "evidence": "asthma",
            "evidence_sentence": "asthma",
            "context": None,
            "modifiers": None,
            "body_site_concept_id": None,
            "body_site_term": None,
        },
    ]

    pgc, _pcalls = _patient_session_with(encounter_row, link_rows)
    kg, kcalls = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "enc-1"},
        )

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["candidate_id"] == hashlib.sha256(deid.encode()).hexdigest()
    assert payload["source"] == "live_encounter_correction"
    assert payload["patient_id"] == "pat-1"
    assert payload["encounter_id"] == "enc-1"
    assert payload["source_coded_links_count"] == 2
    assert payload["entity_count"] == 2
    assert payload["dropped_link_count"] == 0
    assert sorted(payload["baseline_concept_ids"]) == ["195967001", "73211009"]

    upsert = next(
        kwargs for q, kwargs in kcalls if "MERGE (c:TrainingCandidate" in q
    )
    persisted = json.loads(upsert["entities_json"])
    by_concept = {ent["snomed_concept_id"]: ent for ent in persisted}
    assert set(by_concept) == {"73211009", "195967001"}
    diabetes = by_concept["73211009"]
    assert diabetes["label"] == "disorder"
    assert diabetes["semantic_tag"] == "disorder"
    assert diabetes["assertion"] == "present"
    assert deid[diabetes["start"]: diabetes["end"]] == diabetes["text"]
    assert "type 2 diabetes mellitus" in diabetes["text"]


def test_from_encounter_quarantines_whole_note_gold_until_repaired(client):
    raw = "History: cough\nPlan: chest xray requested"
    deid = raw

    encounter_row = {
        "encounter_id": "enc-1",
        "date": "2026-04-18",
        "text": raw,
        "coded_count": 1,
    }
    link_rows = [
        {
            "encounter_id": "enc-1",
            "node_labels": ["Procedure"],
            "concept_id": "168537006",
            "term": "Chest X-ray",
            "read_code": None,
            "semantic_tag": "procedure",
            "evidence": "chest xray",
            "evidence_sentence": "chest xray",
            "context": None,
            "modifiers": None,
            "body_site_concept_id": None,
            "body_site_term": None,
        },
    ]

    pgc, _pcalls = _patient_session_with(encounter_row, link_rows)
    kg, kcalls = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "enc-1"},
        )

    assert r.status_code == 200, r.text
    metadata = [
        kwargs
        for q, kwargs in kcalls
        if "training_quarantined = $training_quarantined" in q
    ]
    assert metadata
    assert metadata[-1]["training_quarantined"] is True
    assert metadata[-1]["annotation_completeness"] == "needs_split"


# -- VT-192-TC-002 -- second call is idempotent (no re-upsert) ----------


def test_second_call_is_idempotent(client):
    raw = "patient attended with cough"
    deid = "patient attended with cough"
    candidate_id = hashlib.sha256(deid.encode()).hexdigest()

    encounter_row = {"encounter_id": "enc-1", "date": "2026-04-18", "text": raw, "coded_count": 0}
    link_rows: list[dict[str, Any]] = []

    existing_candidate = {
        "candidate_id": candidate_id,
        "text": deid,
        "entities_json": "[]",
        "source": "live_encounter_correction",
        "status": "pending",
        "schema_version": "v4",
    }
    existing_label = {"label_id": "manual-existing-9999"}

    pgc, _ = _patient_session_with(encounter_row, link_rows)
    kg, kcalls = _kg_session_capture(
        {
            "MATCH (c:TrainingCandidate {candidate_id: $candidate_id})": (
                existing_candidate
            ),
            "MATCH (g:GoldLabel {candidate_id: $candidate_id})": existing_label,
        }
    )

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "enc-1"},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["candidate_id"] == candidate_id
    assert payload["label_id"] == existing_label["label_id"]
    assert [q for q, _ in kcalls if "MERGE (c:TrainingCandidate" in q] == []
    assert [q for q, _ in kcalls if "MERGE (g:GoldLabel" in q] == []


# -- VT-192-TC-002b -- uncoded encounter ignores stale gold entities ----


def test_uncoded_encounter_returns_live_entities_not_stale_gold(client):
    """Reproduces the "Edit codes on uncoded encounter shows pre-populated
    terms" bug. The GoldLabel for this de-identified text was previously
    populated (either on another encounter that shares the same template
    text, or on this encounter before "Reset and recode"). The editor
    MUST open against the live :DOCUMENTS state, not the stored gold,
    otherwise a silent save writes the stale terms onto a live encounter
    that the card correctly shows as "0 coded concepts".
    """

    raw = "Seen in fast track suspected breast cancer clinic (XaPyQ)"
    deid = raw
    candidate_id = hashlib.sha256(deid.encode()).hexdigest()

    encounter_row = {
        "encounter_id": "enc-uncoded",
        "date": "2025-09-01",
        "text": raw,
        "coded_count": 0,
    }
    link_rows: list[dict[str, Any]] = []

    stale_gold_entities = [
        {
            "text": "Seen in fast track suspected breast cancer clinic",
            "label": "finding",
            "start": 0,
            "end": 50,
            "semantic_tag": "finding",
            "snomed_concept_id": "382431000000103",
            "snomed_term": (
                "Seen in fast track suspected breast cancer clinic (finding)"
            ),
            "assertion": "present",
        }
    ]
    existing_label_row = {
        "label_id": "manual-stale-0001",
        "text": deid,
        "entities_json": json.dumps(stale_gold_entities),
        "quality_score": None,
        "source": "live_encounter_correction",
        "verified_by": "",
        "verified_at": None,
        "candidate_id": candidate_id,
        "schema_version": "v4",
        "created_at": None,
        "updated_at": None,
    }

    pgc, _ = _patient_session_with(encounter_row, link_rows)
    kg, _ = _kg_session_capture(
        {
            "MATCH (c:TrainingCandidate {candidate_id: $candidate_id})": {
                "candidate_id": candidate_id,
                "text": deid,
                "entities_json": "[]",
                "source": "live_encounter_correction",
                "status": "pending",
                "schema_version": "v4",
            },
            "MATCH (g:GoldLabel {candidate_id: $candidate_id})": {
                "label_id": "manual-stale-0001",
            },
            "MATCH (g:GoldLabel {label_id: $label_id})": existing_label_row,
        }
    )

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "enc-uncoded"},
        )

    assert r.status_code == 200, r.text
    payload = r.json()
    # The uncoded live encounter has no baseline -- the editor needs
    # to open empty so the reviewer starts from a blank slate.
    assert payload["baseline_concept_ids"] == []
    assert payload["entity_count"] == 0
    assert payload["source_coded_links_count"] == 0
    # Regression guard: the stored gold entities_json must NOT leak
    # into the editor's initial state for an uncoded encounter.
    returned_entities = json.loads(payload["gold_label"]["entities_json"])
    assert returned_entities == []


# -- VT-192-TC-003 -- missing encounter returns 404 ----------------------


def test_missing_encounter_returns_404(client):
    pgc, _ = _patient_session_with(encounter_row=None, link_rows=[])
    kg, _ = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "missing"},
        )

    assert r.status_code == 404
    assert "Encounter not found" in r.json()["detail"]


# -- VT-192-TC-004 -- encounter with empty text returns 400 --------------


def test_empty_encounter_text_returns_400(client):
    pgc, _ = _patient_session_with(
        encounter_row={"encounter_id": "enc-1", "date": "x", "text": "   ", "coded_count": 0},
        link_rows=[],
    )
    kg, _ = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "enc-1"},
        )

    assert r.status_code == 400
    assert "no text" in r.json()["detail"].lower()


# -- VT-192-TC-005 -- empty patient/encounter ids return 400 -------------


@pytest.mark.parametrize(
    "body",
    [
        {"patient_id": "", "encounter_id": "enc-1"},
        {"patient_id": "pat-1", "encounter_id": ""},
        {"patient_id": "   ", "encounter_id": "enc-1"},
    ],
)
def test_empty_ids_return_400(client, body):
    with caller_scope_override(client.app):
        r = client.post("/training/gold-labels/from-encounter", json=body)
    # pydantic 422 for length-zero strings, 400 for whitespace-stripped
    assert r.status_code in (400, 422)


# -- VT-192-TC-006 -- unmappable links are dropped and counted -----------


def test_unmappable_links_are_dropped_and_counted(client):
    raw = "raw text with PHI"
    deid = "patient attended with cough"

    encounter_row = {
        "encounter_id": "enc-1",
        "date": "x",
        "text": raw,
        "coded_count": 2,
    }
    link_rows = [
        {
            "encounter_id": "enc-1",
            "node_labels": ["Observable_entity"],
            "concept_id": "49727002",
            "term": "Cough",
            "read_code": None,
            "semantic_tag": "observable entity",
            "evidence": "cough",
            "evidence_sentence": "cough",
            "context": None,
            "modifiers": None,
            "body_site_concept_id": None,
            "body_site_term": None,
        },
        {
            "encounter_id": "enc-1",
            "node_labels": ["Disease"],
            "concept_id": "38341003",
            "term": "Hypertension",
            "read_code": None,
            "semantic_tag": "disorder",
            "evidence": "no such phrase",
            "evidence_sentence": "no such phrase",
            "context": None,
            "modifiers": None,
            "body_site_concept_id": None,
            "body_site_term": None,
        },
    ]

    pgc, _ = _patient_session_with(encounter_row, link_rows)
    kg, _ = _kg_session_capture({})

    with (
        caller_scope_override(client.app),
        patch("app.routers.training.PatientGraphClient", return_value=pgc),
        patch("app.routers.training.KnowledgeGraphClient", return_value=kg),
        patch("app.routers.training.deidentify_text", return_value=deid),
        patch("app.routers.training.require_patient_in_scope", return_value=None),
    ):
        r = client.post(
            "/training/gold-labels/from-encounter",
            json={"patient_id": "pat-1", "encounter_id": "enc-1"},
        )

    assert r.status_code == 200
    payload = r.json()
    assert payload["entity_count"] == 1
    assert payload["dropped_link_count"] == 1
    # baseline reflects the live concept_ids regardless of drops, because
    # the optimistic concurrency check needs to see whatever Neo4j has.
    assert sorted(payload["baseline_concept_ids"]) == ["38341003", "49727002"]


# -- VT-192-TC-007 -- semantic tag normalisation -------------------------


def test_semantic_tag_normalisation(client):
    """Spaces and slashes are normalised; unknown tags fall back safely."""

    from app.routers.training import _ner_label_for_semantic_tag

    assert _ner_label_for_semantic_tag("observable entity") == "observable_entity"
    assert _ner_label_for_semantic_tag("regime/therapy") == "regime_therapy"
    assert _ner_label_for_semantic_tag("disorder") == "disorder"
    assert _ner_label_for_semantic_tag(None) == "concept"
    assert _ner_label_for_semantic_tag("") == "concept"
    assert _ner_label_for_semantic_tag("Custom Tag (xyz)") == "custom_tag__xyz"
