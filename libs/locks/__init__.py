"""Reviewer-verification lock primitive.

The ``libs.locks`` package owns the cross-entity ``VerificationLock``
node, the Pydantic data model used by API and UI layers, and
``lock_service.apply_with_lock`` which wraps reviewer mutations,
the lock upsert, and a HumanReconciliation AuditEvent in one
Neo4j transaction.

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

from libs.locks.models import (
    LOCK_ENTITY_TYPES,
    LockEntityType,
    LockReleaseRequest,
    LockSource,
    VerificationLock,
)
from libs.locks.lock_service import (
    LockConflictError,
    LockMutationError,
    apply_with_lock,
    is_locked,
    list_locks_for_episode,
    list_locks_for_patient,
    release_lock,
)

__all__ = [
    "LOCK_ENTITY_TYPES",
    "LockConflictError",
    "LockEntityType",
    "LockMutationError",
    "LockReleaseRequest",
    "LockSource",
    "VerificationLock",
    "apply_with_lock",
    "is_locked",
    "list_locks_for_episode",
    "list_locks_for_patient",
    "release_lock",
]
