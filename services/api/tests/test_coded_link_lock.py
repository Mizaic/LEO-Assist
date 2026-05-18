"""Tests for VerificationLock support on the coded-link endpoints.

Covers:
  - PATCH /coded-links/{concept_id} refuses to recode a locked link (409)
  - PATCH with lock=true wraps the recode in a VerificationLock and returns
    the new lock identity
  - POST /coded-links/{concept_id}/lock action=accept writes a lock keyed
    by (encounter_id, concept_id)
  - POST /coded-links/{concept_id}/lock action=reject releases an existing
    lock and returns released=true
  - Unauthenticated callers cannot write a lock
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import pytest
from fastapi import HTTPException

from app.routers.patients import (
    CodedLinkLockRequest,
    RecodeCodedLinkRequest,
    _coded_link_lock_id,
    lock_or_release_coded_link,
    recode_coded_link,
)

# ---------------------------------------------------------------------------
# Fake harness
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeStore:
    def __init__(self) -> None:
        self.locks: list[dict[str, Any]] = []
        self.recodes: list[dict[str, Any]] = []

    def upsert(self, params: dict[str, Any]) -> dict[str, Any]:
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

    def match(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.locks
            if r["entity_type"] == params["entity_type"]
            and r["entity_id"] == params["entity_id"]
        ]

    def release(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        keep = []
        released = []
        for row in self.locks:
            if row["lock_id"] == params["lock_id"]:
                released.append(dict(row))
            else:
                keep.append(row)
        self.locks = keep
        return released


class _FakeTx:
    def __init__(self, store: _FakeStore):
        self.store = store

    def run(self, query: str, **params: Any) -> _FakeResult:
        if "MERGE (l:VerificationLock" in query:
            return _FakeResult([self.store.upsert(params)])
        if "DELETE l" in query:
            return _FakeResult(self.store.release(params))
        if "MATCH (l:VerificationLock" in query and "DELETE" not in query:
            return _FakeResult(self.store.match(params))
        return _FakeResult([])


class _FakeSession:
    def __init__(self, store: _FakeStore):
        self.store = store

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def run(self, query: str, **params: Any) -> _FakeResult:
        return _FakeTx(self.store).run(query, **params)

    def execute_write(self, fn: Callable[[Any], Any]) -> Any:
        return fn(_FakeTx(self.store))

    def execute_read(self, fn: Callable[[Any], Any]) -> Any:
        return fn(_FakeTx(self.store))


class _FakeClient:
    """Stands in for PatientGraphClient.

    Pre-seed locks via ``preseed_lock`` to simulate an existing reviewer
    lock on the (encounter, concept) pair.
    """

    def __init__(self) -> None:
        self.store = _FakeStore()
        self.match_calls: list[dict[str, Any]] = []

    def preseed_lock(self, *, entity_id: str, locked_by: str = "alice@x") -> None:
        self.store.upsert(
            {
                "entity_type": "coded_link",
                "entity_id": entity_id,
                "lock_id": "lock-existing",
                "locked_by": locked_by,
                "locked_by_role": "clinician",
                "lock_reason": "previously confirmed",
                "source": "encounter_coding_review",
            }
        )

    def session(self) -> _FakeSession:
        return _FakeSession(self.store)

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Scope:
    email = "alice@example.org"
    is_admin = False
    org_ids = ["org-1"]
    primary_org_id = "org-1"

    def to_query_params(self):
        return {"scope_org_ids": ["org-1"]}


def _patch_writer_and_client(monkeypatch, fake_client: _FakeClient) -> None:
    """Patch out the live Neo4j and writer for endpoint tests."""
    from app.routers import patients as p

    monkeypatch.setattr(p, "PatientGraphClient", lambda: fake_client)
    monkeypatch.setattr(p, "require_patient_in_scope", lambda *a, **k: None)

    class _NoopWriter:
        def recode_documents_link(self, **kwargs) -> None:
            fake_client.store.recodes.append(kwargs)

    monkeypatch.setattr(p, "PatientGraphWriter", _NoopWriter)
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )


# ---------------------------------------------------------------------------
# Lock-id helper
# ---------------------------------------------------------------------------


def test_lock_id_uses_composite_key() -> None:
    assert _coded_link_lock_id("enc-1", "12345") == "enc-1:12345"


# ---------------------------------------------------------------------------
# PATCH /coded-links/{concept_id}
# ---------------------------------------------------------------------------


def test_recode_blocks_when_existing_lock_present(monkeypatch) -> None:
    fake = _FakeClient()
    fake.preseed_lock(entity_id="enc-1:111")
    _patch_writer_and_client(monkeypatch, fake)

    body = RecodeCodedLinkRequest(new_concept_id="222", semantic_tag="SnomedConcept")
    with pytest.raises(HTTPException) as ctx:
        recode_coded_link(
            patient_id="pat-1",
            encounter_id="enc-1",
            concept_id="111",
            body=body,
            scope=_Scope(),  # type: ignore[arg-type]
        )
    assert ctx.value.status_code == 409
    detail = ctx.value.detail
    assert isinstance(detail, dict)
    assert detail["lock_id"] == "lock-existing"
    assert "verification-locked" in detail["message"]
    # The recode call must NOT have been issued.
    assert fake.store.recodes == []


def test_recode_with_lock_writes_new_lock_and_recode(monkeypatch) -> None:
    fake = _FakeClient()
    _patch_writer_and_client(monkeypatch, fake)

    body = RecodeCodedLinkRequest(
        new_concept_id="999",
        semantic_tag="SnomedConcept",
        lock=True,
        lock_reason="confirmed in care portal",
        reviewer_role="clinician",
    )
    result = recode_coded_link(
        patient_id="pat-1",
        encounter_id="enc-1",
        concept_id="111",
        body=body,
        scope=_Scope(),  # type: ignore[arg-type]
    )

    assert result["recode"] is True
    assert result["new_concept_id"] == "999"
    assert "lock" in result
    assert result["lock"]["entity_id"] == "enc-1:999"
    assert result["lock"]["entity_type"] == "coded_link"
    # The recode mutation ran inside the same transaction as the lock.
    assert len(fake.store.recodes) == 1
    assert fake.store.recodes[0]["old_concept_id"] == "111"


def test_recode_with_lock_requires_role(monkeypatch) -> None:
    fake = _FakeClient()
    _patch_writer_and_client(monkeypatch, fake)

    body = RecodeCodedLinkRequest(
        new_concept_id="999",
        semantic_tag="SnomedConcept",
        lock=True,
        lock_reason="confirmed",
    )
    with pytest.raises(HTTPException) as ctx:
        recode_coded_link(
            patient_id="pat-1",
            encounter_id="enc-1",
            concept_id="111",
            body=body,
            scope=_Scope(),  # type: ignore[arg-type]
        )
    assert ctx.value.status_code == 400
    assert "reviewer_role" in str(ctx.value.detail)


def test_recode_without_lock_path_is_unaffected(monkeypatch) -> None:
    fake = _FakeClient()
    _patch_writer_and_client(monkeypatch, fake)

    body = RecodeCodedLinkRequest(new_concept_id="999", semantic_tag="SnomedConcept")
    result = recode_coded_link(
        patient_id="pat-1",
        encounter_id="enc-1",
        concept_id="111",
        body=body,
        scope=_Scope(),  # type: ignore[arg-type]
    )

    assert result == {"recode": True, "new_concept_id": "999"}
    assert fake.store.locks == []
    assert len(fake.store.recodes) == 1


# ---------------------------------------------------------------------------
# POST /coded-links/{concept_id}/lock
# ---------------------------------------------------------------------------


def test_lock_accept_writes_lock(monkeypatch) -> None:
    fake = _FakeClient()
    _patch_writer_and_client(monkeypatch, fake)

    body = CodedLinkLockRequest(
        decision="accept", reviewer_role="clinician", reason="reviewed by Dr A"
    )
    result = lock_or_release_coded_link(
        patient_id="pat-1",
        encounter_id="enc-1",
        concept_id="111",
        body=body,
        scope=_Scope(),  # type: ignore[arg-type]
    )

    assert result["decision"] == "accept"
    assert result["entity_id"] == "enc-1:111"
    assert result["lock_id"].startswith("lock-")
    assert len(fake.store.locks) == 1
    assert fake.store.locks[0]["locked_by"] == "alice@example.org"
    assert fake.store.locks[0]["locked_by_role"] == "clinician"


def test_lock_reject_releases_existing_lock(monkeypatch) -> None:
    fake = _FakeClient()
    fake.preseed_lock(entity_id="enc-1:111")
    _patch_writer_and_client(monkeypatch, fake)

    body = CodedLinkLockRequest(
        decision="reject", reviewer_role="qa_ra_lead", reason="bad coding"
    )
    result = lock_or_release_coded_link(
        patient_id="pat-1",
        encounter_id="enc-1",
        concept_id="111",
        body=body,
        scope=_Scope(),  # type: ignore[arg-type]
    )

    assert result == {
        "decision": "reject",
        "released": True,
        "lock_id": "lock-existing",
    }
    assert fake.store.locks == []


def test_lock_reject_when_no_lock_returns_released_false(monkeypatch) -> None:
    fake = _FakeClient()
    _patch_writer_and_client(monkeypatch, fake)

    body = CodedLinkLockRequest(
        decision="reject", reviewer_role="clinician", reason="not needed"
    )
    result = lock_or_release_coded_link(
        patient_id="pat-1",
        encounter_id="enc-1",
        concept_id="111",
        body=body,
        scope=_Scope(),  # type: ignore[arg-type]
    )

    assert result == {"decision": "reject", "released": False}


def test_lock_endpoint_unauthenticated_raises_401(monkeypatch) -> None:
    fake = _FakeClient()
    _patch_writer_and_client(monkeypatch, fake)

    class EmptyScope:
        email = None
        is_admin = False
        org_ids: list[str] = []
        primary_org_id = None

        def to_query_params(self):
            return {}

    body = CodedLinkLockRequest(
        decision="accept", reviewer_role="clinician", reason="confirmed"
    )
    with pytest.raises(HTTPException) as ctx:
        lock_or_release_coded_link(
            patient_id="pat-1",
            encounter_id="enc-1",
            concept_id="111",
            body=body,
            scope=EmptyScope(),  # type: ignore[arg-type]
        )
    assert ctx.value.status_code == 401
