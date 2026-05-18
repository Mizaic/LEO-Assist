"""Reviewer-verification lock service.

``apply_with_lock`` wraps a reviewer mutation, the VerificationLock
upsert, and a HumanReconciliation AuditEvent emission so that every
locked entity has matching audit and graph state. The transactional
guarantee comes from the Neo4j ``execute_write`` helper: the mutation
callable runs inside the same transaction as the lock upsert, and any
exception in either step rolls back the whole unit of work.

The audit event is emitted after the transaction commits, fire and
forget, so audit telemetry failure cannot roll back a successful
graph mutation.

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Iterable, Protocol

from libs.audit.audit_emitter import emit_application_event
from libs.cypher import lock_queries as q
from libs.locks.models import (
    LockEntityType,
    LockSource,
    VerificationLock,
)

logger = logging.getLogger(__name__)


class LockMutationError(RuntimeError):
    """Raised when the reviewer mutation callable fails."""


class LockConflictError(RuntimeError):
    """Raised when an existing lock would prevent a write."""


class _Transaction(Protocol):
    def run(self, query: str, **params: Any) -> Any: ...


class _Session(Protocol):
    def execute_write(
        self, transaction_function: Callable[[_Transaction], Any]
    ) -> Any: ...

    def execute_read(
        self, transaction_function: Callable[[_Transaction], Any]
    ) -> Any: ...

    def __enter__(self) -> "_Session": ...

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...


class _Client(Protocol):
    def session(self) -> _Session: ...


def _new_lock_id() -> str:
    return f"lock-{uuid.uuid4().hex}"


def _record_to_lock(record: dict[str, Any]) -> VerificationLock:
    return VerificationLock(
        lock_id=record["lock_id"],
        entity_type=record["entity_type"],
        entity_id=record["entity_id"],
        locked_by=record["locked_by"],
        locked_by_role=record["locked_by_role"],
        lock_reason=record["lock_reason"],
        source=record["source"],
        locked_at=record["locked_at"],
        updated_at=record["updated_at"],
    )


def _drain(result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in result:
        try:
            rows.append(dict(row))
        except TypeError:
            rows.append(row)
    return rows


def apply_with_lock(
    client: _Client,
    *,
    entity_type: LockEntityType,
    entity_id: str,
    locked_by: str,
    locked_by_role: str,
    lock_reason: str,
    source: LockSource,
    mutation: Callable[[_Transaction], None] | None = None,
) -> VerificationLock:
    """Run mutation + UPSERT_LOCK in one transaction; emit audit event.

    The mutation callable receives the open transaction and is expected
    to issue any number of ``tx.run(...)`` calls. If it raises, the
    whole transaction rolls back and no lock is written. If the lock
    upsert itself fails the same rollback applies.

    The audit event is emitted on the success path only and never
    blocks the response: ``emit_application_event`` already runs the
    HTTP POST in a background thread, and we additionally swallow
    audit-side exceptions so telemetry failure cannot break a
    correctly committed graph write.
    """

    lock_id = _new_lock_id()

    def _txn(tx: _Transaction) -> dict[str, Any]:
        if mutation is not None:
            try:
                mutation(tx)
            except LockConflictError:
                raise
            except Exception as exc:  # rollback drops both mutation and lock
                raise LockMutationError(str(exc)) from exc
        result = tx.run(
            q.UPSERT_LOCK,
            lock_id=lock_id,
            entity_type=entity_type,
            entity_id=entity_id,
            locked_by=locked_by,
            locked_by_role=locked_by_role,
            lock_reason=lock_reason,
            source=source,
        )
        rows = _drain(result)
        if not rows:
            raise LockMutationError("UPSERT_LOCK returned no rows")
        return rows[0]

    with client.session() as session:
        record = session.execute_write(_txn)

    try:
        emit_application_event(
            outcome="0",
            agent_email=locked_by,
            description=(
                f"HumanReconciliation lock entity_type={entity_type} "
                f"entity_id={entity_id} role={locked_by_role} "
                f"source={source} reason={lock_reason}"
            ),
            source_service="lock-service",
            entity_id=entity_id,
            entity_type=entity_type,
        )
    except Exception:  # audit telemetry must never break a committed write
        logger.exception("lock_service: audit emission failed (non-fatal)")

    return _record_to_lock(record)


def is_locked(
    client: _Client,
    *,
    entity_type: LockEntityType,
    entity_id: str,
) -> VerificationLock | None:
    """Return the lock record if one exists, otherwise ``None``."""

    def _txn(tx: _Transaction) -> list[dict[str, Any]]:
        return _drain(
            tx.run(
                q.MATCH_LOCK,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )

    with client.session() as session:
        rows = session.execute_read(_txn)

    if not rows:
        return None
    return _record_to_lock(rows[0])


def release_lock(
    client: _Client,
    *,
    lock_id: str,
    released_by: str,
    released_by_role: str,
    reason: str,
) -> dict[str, str] | None:
    """Delete a lock and emit a HumanReconciliation release audit event."""

    def _txn(tx: _Transaction) -> list[dict[str, Any]]:
        return _drain(tx.run(q.RELEASE_LOCK, lock_id=lock_id))

    with client.session() as session:
        rows = session.execute_write(_txn)

    if not rows:
        return None

    record = rows[0]
    try:
        emit_application_event(
            outcome="0",
            agent_email=released_by,
            description=(
                f"HumanReconciliation release entity_type={record['entity_type']} "
                f"entity_id={record['entity_id']} role={released_by_role} "
                f"reason={reason}"
            ),
            source_service="lock-service",
            entity_id=record["entity_id"],
            entity_type=record["entity_type"],
        )
    except Exception:
        logger.exception("lock_service: release audit emission failed (non-fatal)")

    return {
        "lock_id": record["lock_id"],
        "entity_type": record["entity_type"],
        "entity_id": record["entity_id"],
    }


def list_locks_for_episode(
    client: _Client, *, episode_id: str
) -> list[VerificationLock]:
    """Return every lock attached to an episode and its graph neighbours."""

    def _txn(tx: _Transaction) -> list[dict[str, Any]]:
        return _drain(tx.run(q.LIST_LOCKS_FOR_EPISODE, episode_id=episode_id))

    with client.session() as session:
        rows = session.execute_read(_txn)
    return [_record_to_lock(r) for r in rows]


def list_locks_for_patient(
    client: _Client, *, patient_id: str
) -> list[VerificationLock]:
    """Return every lock visible from a patient's encounters and episodes."""

    def _txn(tx: _Transaction) -> list[dict[str, Any]]:
        return _drain(tx.run(q.LIST_LOCKS_FOR_PATIENT, patient_id=patient_id))

    with client.session() as session:
        rows = session.execute_read(_txn)
    return [_record_to_lock(r) for r in rows]


def filter_locked_entity_ids(
    locks: Iterable[VerificationLock], *, entity_type: LockEntityType
) -> set[str]:
    """Helper for the rebuild guard - extract entity ids of one type."""

    return {lock.entity_id for lock in locks if lock.entity_type == entity_type}
