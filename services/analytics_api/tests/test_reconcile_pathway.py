"""Tests for the PATCH /mission-control/episodes/{id}/reconcile flow.

Covers:
  - bucket-flip safety check returns 412 unless explicitly confirmed
  - confirm action keeps the bucket and writes a lock per slot
  - replace action lands a lock keyed by the new encounter id
  - not-applicable on every diagnosis slot resolves an in_review episode
    to cancer_excluded
  - reviewed_by + reviewer_role are stamped on every lock
  - unknown slot raises 400
  - missing episode raises 404
  - unauthenticated caller raises 401
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import pytest
from fastapi import HTTPException

from libs.episodes.lifecycle import HeroBucket
from libs.episodes.status import EpisodeStatus
from services.analytics_api.app.services.reconcile_pathway import (
    BucketFlipNotConfirmedError,
    EpisodeNotFoundError,
    EpisodeSnapshot,
    ReconcileAction,
    ReconcileRequest,
    UnknownSlotError,
    project_state_after_actions,
    reconcile_episode,
)


# ---------------------------------------------------------------------------
# Fake harness (mirrors tests/locks/test_lock_service.py)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeStore:
    def __init__(self) -> None:
        self.locks: list[dict[str, Any]] = []
        self.tx_committed = 0

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


class _FakeTx:
    def __init__(self, store: _FakeStore) -> None:
        self.store = store
        self.runs: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> _FakeResult:
        self.runs.append((query, params))
        if "MERGE (l:VerificationLock" in query:
            return _FakeResult([self.store.upsert(params)])
        return _FakeResult([])


class _FakeSession:
    def __init__(self, store: _FakeStore) -> None:
        self.store = store

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute_write(self, fn: Callable[[Any], Any]) -> Any:
        tx = _FakeTx(self.store)
        result = fn(tx)
        self.store.tx_committed += 1
        return result

    def execute_read(self, fn: Callable[[Any], Any]) -> Any:
        return fn(_FakeTx(self.store))


class _FakeClient:
    def __init__(self) -> None:
        self.store = _FakeStore()

    def session(self) -> _FakeSession:
        return _FakeSession(self.store)

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _snapshot(
    *,
    status: str = "review",
    has_diag: bool = False,
    benign: bool = False,
    slots: list[dict[str, Any]] | None = None,
    episode_id: str = "ep-1",
) -> EpisodeSnapshot:
    return EpisodeSnapshot(
        episode_id=episode_id,
        status=status,
        has_diagnosis_milestone=has_diag,
        letter_inferred_benign=benign,
        slots=slots
        or [
            {
                "slot": "diagnosis",
                "milestone_type": "diagnosis",
                "encounter_id": "enc-A",
            },
            {
                "slot": "first_treatment",
                "milestone_type": "first_treatment",
                "encounter_id": "enc-B",
            },
        ],
    )


def _request(
    *actions: ReconcileAction,
    confirm_flip: bool = False,
    role: str = "clinician",
) -> ReconcileRequest:
    return ReconcileRequest(
        actions=list(actions),
        reviewed_by="alice@example.org",
        reviewer_role=role,
        reason="reviewed in care portal",
        confirm_bucket_flip=confirm_flip,
    )


# ---------------------------------------------------------------------------
# project_state_after_actions
# ---------------------------------------------------------------------------


def test_project_state_confirm_keeps_diagnosis() -> None:
    snap = _snapshot(has_diag=True)
    proposed = project_state_after_actions(
        snap, [ReconcileAction(slot="diagnosis", action="confirm")]
    )
    assert proposed.has_diagnosis_milestone is True


def test_project_state_replace_swaps_encounter_keeps_diagnosis() -> None:
    snap = _snapshot(has_diag=True)
    proposed = project_state_after_actions(
        snap,
        [
            ReconcileAction(
                slot="diagnosis",
                action="replace",
                encounter_id="enc-NEW",
                milestone_type="diagnosis_confirmed",
            )
        ],
    )
    diag = next(s for s in proposed.slots if s["slot"] == "diagnosis")
    assert diag["encounter_id"] == "enc-NEW"
    assert diag["milestone_type"] == "diagnosis_confirmed"
    assert proposed.has_diagnosis_milestone is True


def test_project_state_detach_removes_diagnosis() -> None:
    snap = _snapshot(has_diag=True)
    proposed = project_state_after_actions(
        snap, [ReconcileAction(slot="diagnosis", action="detach")]
    )
    assert proposed.has_diagnosis_milestone is False


def test_project_state_not_applicable_on_diagnosis_resolves_to_benign() -> None:
    snap = _snapshot(status=EpisodeStatus.REVIEW.value, has_diag=True)
    proposed = project_state_after_actions(
        snap, [ReconcileAction(slot="diagnosis", action="not_applicable")]
    )
    assert proposed.has_diagnosis_milestone is False
    assert proposed.status == EpisodeStatus.CLOSED_BENIGN.value


def test_project_state_unknown_slot_raises() -> None:
    snap = _snapshot()
    with pytest.raises(UnknownSlotError):
        project_state_after_actions(
            snap, [ReconcileAction(slot="nonexistent", action="confirm")]
        )


# ---------------------------------------------------------------------------
# reconcile_episode
# ---------------------------------------------------------------------------


def _stub_reader(snapshot: EpisodeSnapshot | None) -> Callable[[str], Any]:
    return lambda episode_id: snapshot


def test_reconcile_writes_one_lock_per_action(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot(has_diag=True)
    client = _FakeClient()

    result = reconcile_episode(
        episode_id="ep-1",
        request=_request(
            ReconcileAction(slot="diagnosis", action="confirm"),
            ReconcileAction(slot="first_treatment", action="confirm"),
        ),
        snapshot_reader=_stub_reader(snap),
        lock_client=client,
    )

    assert len(result.locks) == 2
    assert client.store.tx_committed == 2
    assert result.bucket is HeroBucket.CONFIRMED_CANCER
    assert result.flip.flips is False
    for lock in result.locks:
        assert lock.entity_type == "is_part_of_edge"
        assert lock.locked_by == "alice@example.org"
        assert lock.locked_by_role == "clinician"
        assert lock.source == "reconcile_pathway"


def test_reconcile_replace_lock_uses_new_encounter_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot(has_diag=True)
    client = _FakeClient()

    result = reconcile_episode(
        episode_id="ep-1",
        request=_request(
            ReconcileAction(
                slot="diagnosis", action="replace", encounter_id="enc-NEW"
            )
        ),
        snapshot_reader=_stub_reader(snap),
        lock_client=client,
    )

    assert result.locks[0].entity_id == "enc-NEW:ep-1"


def test_reconcile_unfilled_slot_uses_placeholder_in_lock_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot(
        slots=[
            {
                "slot": "diagnosis",
                "milestone_type": "diagnosis",
                "encounter_id": None,
            }
        ]
    )
    client = _FakeClient()

    result = reconcile_episode(
        episode_id="ep-1",
        request=_request(
            ReconcileAction(slot="diagnosis", action="not_applicable"),
            confirm_flip=True,
        ),
        snapshot_reader=_stub_reader(snap),
        lock_client=client,
    )

    assert result.locks[0].entity_id == "__unfilled__:ep-1"


def test_reconcile_refuses_silent_bucket_flip(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot(status=EpisodeStatus.REVIEW.value, has_diag=True)
    client = _FakeClient()

    with pytest.raises(BucketFlipNotConfirmedError) as ctx:
        reconcile_episode(
            episode_id="ep-1",
            request=_request(
                ReconcileAction(slot="diagnosis", action="not_applicable"),
            ),
            snapshot_reader=_stub_reader(snap),
            lock_client=client,
        )
    assert ctx.value.flip.current_bucket is HeroBucket.CONFIRMED_CANCER
    assert ctx.value.flip.proposed_bucket is HeroBucket.CANCER_EXCLUDED
    assert client.store.locks == []


def test_reconcile_confirms_explicit_bucket_flip(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot(status=EpisodeStatus.REVIEW.value, has_diag=True)
    client = _FakeClient()

    result = reconcile_episode(
        episode_id="ep-1",
        request=_request(
            ReconcileAction(slot="diagnosis", action="not_applicable"),
            confirm_flip=True,
        ),
        snapshot_reader=_stub_reader(snap),
        lock_client=client,
    )

    assert result.bucket is HeroBucket.CANCER_EXCLUDED
    assert result.flip.flips is True
    assert len(client.store.locks) == 1


def test_reconcile_episode_not_found_raises() -> None:
    with pytest.raises(EpisodeNotFoundError):
        reconcile_episode(
            episode_id="ep-missing",
            request=_request(ReconcileAction(slot="diagnosis", action="confirm")),
            snapshot_reader=_stub_reader(None),
            lock_client=_FakeClient(),
        )


def test_reconcile_unknown_slot_raises_before_writing_locks(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot()
    client = _FakeClient()

    with pytest.raises(UnknownSlotError):
        reconcile_episode(
            episode_id="ep-1",
            request=_request(ReconcileAction(slot="ghost", action="confirm")),
            snapshot_reader=_stub_reader(snap),
            lock_client=client,
        )
    assert client.store.locks == []


def test_reconcile_qa_role_stamps_role_on_lock(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )
    snap = _snapshot(has_diag=True)
    client = _FakeClient()

    result = reconcile_episode(
        episode_id="ep-1",
        request=_request(
            ReconcileAction(slot="diagnosis", action="confirm"),
            role="qa_ra_lead",
        ),
        snapshot_reader=_stub_reader(snap),
        lock_client=client,
    )

    assert result.locks[0].locked_by_role == "qa_ra_lead"


# ---------------------------------------------------------------------------
# Router-level surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_endpoint_unauthenticated_returns_401() -> None:
    from services.analytics_api.app.routers.mission_control import (
        patch_episode_reconcile,
    )

    class EmptyScope:
        email = None
        is_admin = False
        org_ids: list[str] = []
        primary_org_id = None

        def to_query_params(self):
            return {}

    body = _request(ReconcileAction(slot="diagnosis", action="confirm"))
    with pytest.raises(HTTPException) as ctx:
        await patch_episode_reconcile("ep-1", body, scope=EmptyScope())  # type: ignore[arg-type]
    assert ctx.value.status_code == 401


@pytest.mark.asyncio
async def test_patch_endpoint_invalid_episode_id_returns_400() -> None:
    from services.analytics_api.app.routers.mission_control import (
        patch_episode_reconcile,
    )

    class _Scope:
        email = "alice@example.org"
        is_admin = False
        org_ids = ["org-1"]
        primary_org_id = "org-1"

        def to_query_params(self):
            return {"scope_org_ids": ["org-1"]}

    body = _request(ReconcileAction(slot="diagnosis", action="confirm"))
    with pytest.raises(HTTPException) as ctx:
        await patch_episode_reconcile("bad id; DROP", body, scope=_Scope())  # type: ignore[arg-type]
    assert ctx.value.status_code == 400


@pytest.mark.asyncio
async def test_patch_endpoint_translates_412(monkeypatch) -> None:
    from services.analytics_api.app.routers import mission_control as mc

    snap = _snapshot(status=EpisodeStatus.REVIEW.value, has_diag=True)
    monkeypatch.setattr(mc, "_read_reconcile_snapshot", lambda _eid: snap)
    monkeypatch.setattr(mc, "PatientGraphClient", _FakeClient)
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )

    class _Scope:
        email = "alice@example.org"
        is_admin = False
        org_ids = ["org-1"]
        primary_org_id = "org-1"

        def to_query_params(self):
            return {"scope_org_ids": ["org-1"]}

    body = _request(ReconcileAction(slot="diagnosis", action="not_applicable"))
    with pytest.raises(HTTPException) as ctx:
        await mc.patch_episode_reconcile("ep-1", body, scope=_Scope())  # type: ignore[arg-type]
    assert ctx.value.status_code == 412
    detail = ctx.value.detail
    assert isinstance(detail, dict)
    assert detail["current_bucket"] == "confirmed_cancer"
    assert detail["proposed_bucket"] == "cancer_excluded"


@pytest.mark.asyncio
async def test_patch_endpoint_returns_lock_ids_on_success(monkeypatch) -> None:
    from services.analytics_api.app.routers import mission_control as mc

    snap = _snapshot(has_diag=True)
    monkeypatch.setattr(mc, "_read_reconcile_snapshot", lambda _eid: snap)
    monkeypatch.setattr(mc, "PatientGraphClient", _FakeClient)
    monkeypatch.setattr(
        "libs.locks.lock_service.emit_application_event", lambda **kw: None
    )

    class _Scope:
        email = "alice@example.org"
        is_admin = False
        org_ids = ["org-1"]
        primary_org_id = "org-1"

        def to_query_params(self):
            return {"scope_org_ids": ["org-1"]}

    body = _request(
        ReconcileAction(slot="diagnosis", action="confirm"),
        ReconcileAction(slot="first_treatment", action="confirm"),
    )
    response = await mc.patch_episode_reconcile("ep-1", body, scope=_Scope())  # type: ignore[arg-type]

    assert response["episode_id"] == "ep-1"
    assert response["bucket"] == "confirmed_cancer"
    assert response["flipped"] is False
    assert len(response["locks"]) == 2
    assert {lock["slot"] for lock in response["locks"]} == {
        "diagnosis",
        "first_treatment",
    }
    assert all(lock["entity_type"] == "is_part_of_edge" for lock in response["locks"])
    assert all(lock["lock_id"].startswith("lock-") for lock in response["locks"])
