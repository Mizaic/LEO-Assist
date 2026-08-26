"""Unit tests for libs.locks.lock_service.

These tests use an in-memory fake Neo4j session/transaction so we can
exercise the transactional, audit and rollback contracts without
needing a real graph database. The fake matches the surface that
``apply_with_lock`` actually calls: ``client.session()``,
``session.execute_write(fn)`` / ``execute_read(fn)``, and ``tx.run(...)``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from libs.locks import (
    LOCK_ENTITY_TYPES,
    LockMutationError,
    VerificationLock,
    apply_with_lock,
    is_locked,
    list_locks_for_episode,
    list_locks_for_patient,
    release_lock,
)
from libs.cypher import lock_queries as q


# ---------------------------------------------------------------------------
# Fake Neo4j harness
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeTx:
    def __init__(self, store: "_FakeStore", *, fail_on: set[str] | None = None):
        self.store = store
        self.runs: list[tuple[str, dict[str, Any]]] = []
        self.fail_on = fail_on or set()

    def run(self, query: str, **params: Any) -> _FakeResult:
        self.runs.append((query, params))
        if any(token in query for token in self.fail_on):
            raise RuntimeError(f"forced failure on query containing {self.fail_on}")
        if query is q.UPSERT_LOCK or "MERGE (l:VerificationLock" in query:
            return _FakeResult([self.store.upsert_lock(params)])
        if query is q.MATCH_LOCK:
            return _FakeResult(self.store.match_lock(params))
        if query is q.RELEASE_LOCK:
            return _FakeResult(self.store.release_lock(params))
        if query is q.LIST_LOCKS_FOR_EPISODE:
            return _FakeResult(self.store.list_for_episode(params))
        if query is q.LIST_LOCKS_FOR_PATIENT:
            return _FakeResult(self.store.list_for_patient(params))
        return _FakeResult([])


class _FakeStore:
    def __init__(self) -> None:
        self.locks: list[dict[str, Any]] = []
        self.tx_committed = 0
        self.tx_rolled_back = 0
        self.episode_lookup: dict[str, list[str]] = {}
        self.patient_lookup: dict[str, list[str]] = {}

    def upsert_lock(self, params: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        for row in self.locks:
            if (
                row["entity_type"] == params["entity_type"]
                and row["entity_id"] == params["entity_id"]
            ):
                row.update(
                    locked_by=params["locked_by"],
                    locked_by_role=params["locked_by_role"],
                    lock_reason=params["lock_reason"],
                    source=params["source"],
                    updated_at=now,
                )
                return dict(row)
        row = {
            "lock_id": params["lock_id"],
            "entity_type": params["entity_type"],
            "entity_id": params["entity_id"],
            "locked_by": params["locked_by"],
            "locked_by_role": params["locked_by_role"],
            "lock_reason": params["lock_reason"],
            "source": params["source"],
            "locked_at": now,
            "updated_at": now,
        }
        self.locks.append(row)
        return dict(row)

    def match_lock(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.locks
            if r["entity_type"] == params["entity_type"]
            and r["entity_id"] == params["entity_id"]
        ]

    def release_lock(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        keep: list[dict[str, Any]] = []
        released: list[dict[str, Any]] = []
        for row in self.locks:
            if row["lock_id"] == params["lock_id"]:
                released.append(dict(row))
            else:
                keep.append(row)
        self.locks = keep
        return released

    def list_for_episode(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        ids = set(self.episode_lookup.get(params["episode_id"], []))
        return [dict(r) for r in self.locks if r["entity_id"] in ids]

    def list_for_patient(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        ids = set(self.patient_lookup.get(params["patient_id"], []))
        return [dict(r) for r in self.locks if r["entity_id"] in ids]


class _FakeSession:
    def __init__(self, store: _FakeStore, *, fail_on: set[str] | None = None) -> None:
        self.store = store
        self.fail_on = fail_on

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def execute_write(self, fn: Callable[[Any], Any]) -> Any:
        tx = _FakeTx(self.store, fail_on=self.fail_on)
        try:
            result = fn(tx)
        except Exception:
            self.store.tx_rolled_back += 1
            raise
        self.store.tx_committed += 1
        return result

    def execute_read(self, fn: Callable[[Any], Any]) -> Any:
        tx = _FakeTx(self.store, fail_on=self.fail_on)
        return fn(tx)


class _FakeClient:
    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.store = _FakeStore()
        self.fail_on = fail_on

    def session(self) -> _FakeSession:
        return _FakeSession(self.store, fail_on=self.fail_on)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_lock_entity_type_vocabulary_is_complete() -> None:
    assert set(LOCK_ENTITY_TYPES) == {
        "episode",
        "encounter",
        "is_part_of_edge",
        "coded_link",
        "assertion",
    }


def test_verification_lock_rejects_blank_entity_id() -> None:
    with pytest.raises(ValidationError):
        VerificationLock(
            lock_id="lock-12345678",
            entity_type="encounter",
            entity_id="",
            locked_by="alice@x",
            locked_by_role="clinician",
            lock_reason="confirmed",
            source="reconcile_pathway",
            locked_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# apply_with_lock
# ---------------------------------------------------------------------------


def _apply(client: _FakeClient, **overrides: Any) -> VerificationLock:
    kwargs = dict(
        entity_type="encounter",
        entity_id="enc-123",
        locked_by="alice@example.org",
        locked_by_role="clinician",
        lock_reason="confirmed during reconcile",
        source="reconcile_pathway",
    )
    kwargs.update(overrides)
    return apply_with_lock(client, **kwargs)


def test_apply_with_lock_writes_lock_and_emits_audit(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event",
        lambda **kw: captured.append(kw),
    )
    client = _FakeClient()

    lock = _apply(client)

    assert isinstance(lock, VerificationLock)
    assert lock.entity_type == "encounter"
    assert lock.entity_id == "enc-123"
    assert lock.locked_by_role == "clinician"
    assert lock.source == "reconcile_pathway"
    assert lock.lock_id.startswith("lock-")
    assert client.store.tx_committed == 1
    assert client.store.tx_rolled_back == 0
    assert len(captured) == 1
    audit = captured[0]
    assert audit["entity_id"] == "enc-123"
    assert audit["entity_type"] == "encounter"
    assert "HumanReconciliation lock" in audit["description"]
    assert "role=clinician" in audit["description"]


def test_apply_with_lock_runs_mutation_in_same_transaction(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    client = _FakeClient()

    seen_runs: list[str] = []

    def mutation(tx: Any) -> None:
        tx.run("MATCH (e:Encounter {id: $id}) SET e.confirmed = true", id="enc-9")
        seen_runs.append("mutation-ran")

    lock = _apply(client, entity_id="enc-9", mutation=mutation)

    assert lock.entity_id == "enc-9"
    assert seen_runs == ["mutation-ran"]
    assert client.store.tx_committed == 1


def test_apply_with_lock_idempotent_on_repeat_call(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    client = _FakeClient()

    first = _apply(client, lock_reason="confirmed")
    second = _apply(client, lock_reason="re-confirmed by QA")

    assert len(client.store.locks) == 1
    assert client.store.locks[0]["lock_reason"] == "re-confirmed by QA"
    assert first.entity_id == second.entity_id == "enc-123"
    assert client.store.tx_committed == 2


def test_apply_with_lock_rolls_back_on_mutation_failure(monkeypatch) -> None:
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event",
        lambda **kw: audits.append(kw),
    )
    client = _FakeClient()

    def boom(tx: Any) -> None:
        tx.run("SET something", payload="x")
        raise RuntimeError("write failed")

    with pytest.raises(LockMutationError):
        _apply(client, mutation=boom)

    assert client.store.locks == []
    assert client.store.tx_committed == 0
    assert client.store.tx_rolled_back == 1
    assert audits == []


def test_apply_with_lock_audit_failure_does_not_break_commit(monkeypatch) -> None:
    def explode(**kw: Any) -> None:
        raise RuntimeError("audit pipeline down")

    monkeypatch.setattr("libs.locks.lock_service.emit_application_event", explode)
    client = _FakeClient()

    lock = _apply(client)

    assert client.store.tx_committed == 1
    assert lock.entity_id == "enc-123"
    assert len(client.store.locks) == 1


def test_apply_with_lock_stamps_role_in_audit_description(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event",
        lambda **kw: captured.append(kw),
    )
    client = _FakeClient()

    _apply(client, locked_by_role="regulatory_reviewer", source="qa_override")

    assert "role=regulatory_reviewer" in captured[0]["description"]
    assert "source=qa_override" in captured[0]["description"]


# ---------------------------------------------------------------------------
# is_locked / release_lock / listing
# ---------------------------------------------------------------------------


def test_is_locked_returns_lock_when_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    client = _FakeClient()
    _apply(client, entity_type="coded_link", entity_id="enc-1:1234")

    found = is_locked(client, entity_type="coded_link", entity_id="enc-1:1234")
    missing = is_locked(client, entity_type="coded_link", entity_id="enc-1:9999")

    assert found is not None
    assert found.entity_id == "enc-1:1234"
    assert missing is None


def test_release_lock_removes_lock_and_emits_audit(monkeypatch) -> None:
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event",
        lambda **kw: audits.append(kw),
    )
    client = _FakeClient()
    lock = _apply(client)

    result = release_lock(
        client,
        lock_id=lock.lock_id,
        released_by="alice@example.org",
        released_by_role="clinician",
        reason="found a coding error",
    )

    assert result == {
        "lock_id": lock.lock_id,
        "entity_type": "encounter",
        "entity_id": "enc-123",
    }
    assert client.store.locks == []
    assert any("HumanReconciliation release" in a["description"] for a in audits)


def test_release_lock_returns_none_when_lock_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    client = _FakeClient()

    result = release_lock(
        client,
        lock_id="lock-does-not-exist",
        released_by="alice@example.org",
        released_by_role="clinician",
        reason="cleanup",
    )

    assert result is None


def test_list_locks_for_episode_returns_only_locks_in_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    client = _FakeClient()
    client.store.episode_lookup["ep-A"] = ["ep-A", "enc-1", "enc-2"]
    client.store.episode_lookup["ep-B"] = ["ep-B"]
    _apply(client, entity_type="episode", entity_id="ep-A")
    _apply(client, entity_type="encounter", entity_id="enc-1")
    _apply(client, entity_type="episode", entity_id="ep-B")

    locks = list_locks_for_episode(client, episode_id="ep-A")

    ids = sorted(lock.entity_id for lock in locks)
    assert ids == ["enc-1", "ep-A"]


def test_list_locks_for_patient_walks_patient_graph(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    client = _FakeClient()
    client.store.patient_lookup["pat-7"] = ["enc-1", "ep-A"]
    _apply(client, entity_type="episode", entity_id="ep-A")
    _apply(client, entity_type="encounter", entity_id="enc-1")
    _apply(client, entity_type="encounter", entity_id="enc-other")

    locks = list_locks_for_patient(client, patient_id="pat-7")
    ids = sorted(lock.entity_id for lock in locks)

    assert ids == ["enc-1", "ep-A"]
