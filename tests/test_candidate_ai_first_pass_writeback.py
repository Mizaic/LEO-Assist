"""VT-LEO-AI-200 -- AI first-pass writeback + delete TOCTOU defence.

Cases:
  TC-011: writeback_pre_done is write-once on entities_json_original.
  TC-012: execute_delete refuses to delete status='completed'.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest

from libs.cypher.training_candidate_queries import (
    DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS,
    GET_TRAINING_CANDIDATE_BY_ID,
    UPSERT_AI_FIRST_PASS_ENTITIES,
)
from services.api.app.services.candidate_ai_first_pass._writeback import (
    execute_delete,
    writeback_pre_done,
)


# ---------- fakes -----------------------------------------------------------


class _FakeResult:
    def __init__(self, row: dict[str, Any] | None):
        # Neo4j Record supports dict(row); a plain dict satisfies the
        # writeback layer's `dict(row)` and `.get()` usages directly.
        self._row = dict(row) if row is not None else None

    def single(self):
        return self._row


class _FakeSession:
    """Records every (cypher, params) and returns canned results in order."""

    def __init__(self, plan: list[Any]):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._plan = list(plan)

    def run(self, cypher: str, **params) -> _FakeResult:
        self.calls.append((cypher, dict(params)))
        if not self._plan:
            return _FakeResult(None)
        nxt = self._plan.pop(0)
        return _FakeResult(nxt)

    def close(self):
        return None


class _FakeClient:
    def __init__(self, sessions: list[_FakeSession]):
        self._sessions = sessions

    @contextmanager
    def session(self):
        s = self._sessions.pop(0)
        try:
            yield s
        finally:
            s.close()


# ---------- TC-011: write-once invariant ------------------------------------


def test_VT_194_TC_011_writeback_is_write_once_on_entities_json_original():
    """Two consecutive writebacks both must succeed; the audit copy field
    is set on the first call (Cypher CASE ... WHEN IS NULL ...) and is
    NOT overwritten by the second. We can't enforce that at the Python
    layer (Cypher does it), but we CAN verify the writeback function
    sends the SAME UPSERT_AI_FIRST_PASS_ENTITIES query both times,
    confirming we never branch into 'overwrite original' logic."""
    payload_v1 = [
        {"text": "diabetes", "label": "disorder", "ai_first_pass": True},
    ]
    payload_v2 = [
        {"text": "diabetes mellitus type 2", "label": "disorder", "ai_first_pass": True},
    ]

    session_1 = _FakeSession(
        [
            {"candidate_id": "c1", "status": "pending"},  # GET_BY_ID TOCTOU
            {  # UPSERT result
                "candidate_id": "c1",
                "status": "pending",
                "ai_first_pass_run_id": "run-1",
                "ai_first_pass_at": "2026-04-17T20:00:00Z",
                "audit_copy_present": True,
            },
        ]
    )
    session_2 = _FakeSession(
        [
            {"candidate_id": "c1", "status": "pending"},
            {
                "candidate_id": "c1",
                "status": "pending",
                "ai_first_pass_run_id": "run-2",
                "ai_first_pass_at": "2026-04-17T20:05:00Z",
                "audit_copy_present": True,
            },
        ]
    )
    client = _FakeClient([session_1, session_2])

    out_1 = writeback_pre_done(
        client, candidate_id="c1", entities_payload=payload_v1, run_id="run-1"
    )
    out_2 = writeback_pre_done(
        client, candidate_id="c1", entities_payload=payload_v2, run_id="run-2"
    )

    assert out_1["action"] == "upserted_pre_done"
    assert out_2["action"] == "upserted_pre_done"

    # Both calls used UPSERT_AI_FIRST_PASS_ENTITIES Cypher (which itself
    # has the IS NULL CASE for the audit copy).
    upserts_1 = [c for c in session_1.calls if c[0] == UPSERT_AI_FIRST_PASS_ENTITIES]
    upserts_2 = [c for c in session_2.calls if c[0] == UPSERT_AI_FIRST_PASS_ENTITIES]
    assert len(upserts_1) == 1
    assert len(upserts_2) == 1
    assert upserts_1[0][1]["run_id"] == "run-1"
    assert upserts_2[0][1]["run_id"] == "run-2"
    assert json.loads(upserts_1[0][1]["entities_json"])[0]["text"] == "diabetes"
    assert (
        json.loads(upserts_2[0][1]["entities_json"])[0]["text"]
        == "diabetes mellitus type 2"
    )


def test_writeback_skips_when_status_is_completed_at_toctou_recheck():
    session = _FakeSession([{"candidate_id": "c2", "status": "completed"}])
    client = _FakeClient([session])

    out = writeback_pre_done(
        client,
        candidate_id="c2",
        entities_payload=[{"text": "x", "label": "finding"}],
        run_id="run-x",
    )

    assert out["action"] == "skipped_completed"
    cyphers = [c[0] for c in session.calls]
    assert UPSERT_AI_FIRST_PASS_ENTITIES not in cyphers


def test_writeback_returns_not_found_when_candidate_missing():
    session = _FakeSession([None])
    client = _FakeClient([session])

    out = writeback_pre_done(
        client,
        candidate_id="missing",
        entities_payload=[{"text": "x", "label": "finding"}],
        run_id="run",
    )

    assert out["action"] == "not_found"
    assert out["candidate_id"] == "missing"


# ---------- TC-012: execute_delete TOCTOU defence ---------------------------


def test_VT_194_TC_012_execute_delete_refuses_to_delete_completed():
    session = _FakeSession([{"candidate_id": "gold-1", "status": "completed"}])
    client = _FakeClient([session])

    out = execute_delete(client, "gold-1")

    assert out["action"] == "skipped_completed"
    cyphers = [c[0] for c in session.calls]
    assert DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS not in cyphers


def test_execute_delete_runs_delete_when_status_not_completed():
    session = _FakeSession(
        [
            {"candidate_id": "c-del", "status": "pending"},
            {
                "candidate_id": "c-del",
                "gold_labels_deleted": 1,
                "surface_form_tasks_deleted": 0,
            },
        ]
    )
    client = _FakeClient([session])

    out = execute_delete(client, "c-del")

    assert out["action"] == "deleted"
    assert out["gold_labels_deleted"] == 1
    cyphers = [c[0] for c in session.calls]
    assert GET_TRAINING_CANDIDATE_BY_ID in cyphers
    assert DELETE_TRAINING_CANDIDATE_AND_ARTIFACTS in cyphers


@pytest.mark.parametrize("bad_id", ["", None])
def test_writeback_rejects_empty_candidate_id(bad_id):
    out = writeback_pre_done(
        _FakeClient([]), candidate_id=bad_id, entities_payload=[], run_id="r"
    )
    assert out["action"] == "error"
