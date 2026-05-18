"""Reconcile-pathway service for /mission-control/episodes/{id}/reconcile.

The router stays thin: it parses the request, delegates to
``reconcile_episode``, and turns service-layer exceptions into HTTP
responses. The service is responsible for:

  - reading the live state of the episode from the patient graph;
  - simulating the proposed milestone-slot actions against that state;
  - calling :func:`libs.episodes.lifecycle.would_flip_bucket` and
    refusing to write if the proposal would silently move the episode
    into a different hero bucket without explicit reviewer
    confirmation;
  - per-action, calling :func:`libs.locks.lock_service.apply_with_lock`
    so each milestone-slot mutation lands inside the same transaction
    as the matching VerificationLock write and HumanReconciliation
    audit event.

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  DI: DI-9DCC9F84 (Reconcile pathway)
  VT: VT-96455BC1 (lock service)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Literal, Optional, Protocol

from pydantic import BaseModel, Field

from libs.episodes.lifecycle import (
    BucketFlip,
    HeroBucket,
    would_flip_bucket,
)
from libs.episodes.status import EpisodeStatus
from libs.locks import LockSource, VerificationLock, apply_with_lock

logger = logging.getLogger(__name__)


ReconcileActionType = Literal["confirm", "replace", "detach", "not_applicable"]


class ReconcileAction(BaseModel):
    """One reviewer decision for a single milestone slot."""

    slot: str = Field(..., min_length=1, max_length=64)
    action: ReconcileActionType
    encounter_id: Optional[str] = Field(default=None, max_length=128)
    milestone_type: Optional[str] = Field(default=None, max_length=64)


class ReconcileRequest(BaseModel):
    """Body for ``PATCH /mission-control/episodes/{id}/reconcile``."""

    actions: list[ReconcileAction] = Field(..., min_length=1)
    reviewed_by: str = Field(..., min_length=1)
    reviewer_role: Literal["clinician", "qa_ra_lead"]
    reason: str = Field(..., min_length=1, max_length=500)
    confirm_bucket_flip: bool = False


class EpisodeSnapshot(BaseModel):
    """Read-side snapshot of an EpisodeOfCare used by the bucket flip
    safety check.

    Each ``slots`` entry represents a single milestone slot that the
    reviewer can act on. ``encounter_id`` may be ``None`` when the
    slot is currently unfilled (the engine flagged the episode for
    review specifically because no encounter could be assigned).
    """

    episode_id: str
    status: Optional[str]
    has_diagnosis_milestone: bool
    letter_inferred_benign: bool
    slots: list[dict[str, Optional[str]]]


class ReconcileResult(BaseModel):
    """Service-level success result returned to the router."""

    episode_id: str
    bucket: HeroBucket
    flip: BucketFlip
    locks: list[VerificationLock]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReconcileError(RuntimeError):
    """Base class for reconcile-pathway service errors."""


class EpisodeNotFoundError(ReconcileError):
    """Raised when no EpisodeOfCare with the given id exists."""


class BucketFlipNotConfirmedError(ReconcileError):
    """Raised when the proposed actions would flip lifecycle buckets and
    the client did not pass ``confirm_bucket_flip=True``.
    """

    def __init__(self, flip: BucketFlip):
        super().__init__(
            f"Proposed actions would move episode from "
            f"{flip.current_bucket.value} to {flip.proposed_bucket.value}; "
            "client must set confirm_bucket_flip=true"
        )
        self.flip = flip


class UnknownSlotError(ReconcileError):
    """Raised when an action targets a slot that is not on the episode."""


# ---------------------------------------------------------------------------
# Reader / mutator contracts
# ---------------------------------------------------------------------------


class _SnapshotReader(Protocol):
    def __call__(self, episode_id: str) -> EpisodeSnapshot | None: ...


class _LockClient(Protocol):
    def session(self) -> Any: ...


# ---------------------------------------------------------------------------
# Pure helpers (testable without a graph)
# ---------------------------------------------------------------------------


def _slot_lock_id(episode_id: str, slot_encounter_id: Optional[str]) -> str:
    """Return the composite key used for ``is_part_of_edge`` locks."""

    return f"{slot_encounter_id or '__unfilled__'}:{episode_id}"


def project_state_after_actions(
    snapshot: EpisodeSnapshot, actions: list[ReconcileAction]
) -> EpisodeSnapshot:
    """Compute the state the episode would have once ``actions`` apply.

    The projection is intentionally narrow: it only updates fields the
    reconcile flow can change, and only the fields the lifecycle helper
    consumes -- the bucket flip safety check needs ``status``,
    ``has_diagnosis_milestone`` and ``letter_inferred_benign`` to
    decide whether the proposal silently changes the dashboard cohort.
    The actual graph mutations happen later inside
    :func:`apply_with_lock`.
    """

    diagnosis_terms = {"diagnosis", "diagnosis_confirmed"}
    slot_index = {row.get("slot"): dict(row) for row in snapshot.slots}

    for action in actions:
        slot_row = slot_index.get(action.slot)
        if slot_row is None:
            raise UnknownSlotError(
                f"Action targets unknown slot {action.slot!r} on episode "
                f"{snapshot.episode_id!r}"
            )
        if action.action == "confirm":
            continue
        if action.action == "replace":
            slot_row["encounter_id"] = action.encounter_id
            slot_row["milestone_type"] = action.milestone_type or slot_row.get(
                "milestone_type"
            )
        elif action.action == "detach":
            slot_row["encounter_id"] = None
        elif action.action == "not_applicable":
            slot_row["encounter_id"] = None
            slot_row["milestone_type"] = "not_applicable"

    has_diagnosis = any(
        (row.get("milestone_type") in diagnosis_terms)
        and row.get("encounter_id") not in (None, "")
        for row in slot_index.values()
    )

    proposed_status = snapshot.status
    if not has_diagnosis and snapshot.status == EpisodeStatus.REVIEW.value:
        # Marking every diagnosis slot as not-applicable resolves the
        # review without committing a confirmed cancer outcome.
        proposed_status = EpisodeStatus.CLOSED_BENIGN.value

    return EpisodeSnapshot(
        episode_id=snapshot.episode_id,
        status=proposed_status,
        has_diagnosis_milestone=has_diagnosis,
        letter_inferred_benign=snapshot.letter_inferred_benign,
        slots=list(slot_index.values()),
    )


# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------


def reconcile_episode(
    *,
    episode_id: str,
    request: ReconcileRequest,
    snapshot_reader: _SnapshotReader,
    lock_client: _LockClient,
    mutation_factory: (
        Callable[[str, ReconcileAction, EpisodeSnapshot], Callable[[Any], None]] | None
    ) = None,
    source: LockSource = "reconcile_pathway",
) -> ReconcileResult:
    """Apply each reconcile action with a matching VerificationLock.

    Parameters
    ----------
    episode_id:
        Target ``EpisodeOfCare.episode_id``.
    request:
        Validated reconcile body.
    snapshot_reader:
        Callable returning the live :class:`EpisodeSnapshot` (or
        ``None`` if the episode does not exist). Injected so unit
        tests can swap in a fake reader.
    lock_client:
        Neo4j-style client passed straight through to
        :func:`libs.locks.lock_service.apply_with_lock`.
    mutation_factory:
        Optional factory that turns one action plus its episode
        snapshot into the actual graph-mutation callable. The default
        ``None`` means the lock service writes only the
        VerificationLock and the audit event -- useful for tests and
        for the first phase of the reconcile rollout where the slot
        mutations happen via a separate writer.
    source:
        VerificationLock ``source`` field (default
        ``reconcile_pathway``).

    Returns
    -------
    ReconcileResult with the post-write bucket and the list of locks
    written.

    Raises
    ------
    EpisodeNotFoundError, UnknownSlotError, BucketFlipNotConfirmedError.
    """

    snapshot = snapshot_reader(episode_id)
    if snapshot is None:
        raise EpisodeNotFoundError(f"Episode {episode_id!r} not found in patient graph")

    proposed = project_state_after_actions(snapshot, request.actions)

    flip = would_flip_bucket(
        current_status=snapshot.status,
        current_has_diagnosis_milestone=snapshot.has_diagnosis_milestone,
        current_letter_inferred_benign=snapshot.letter_inferred_benign,
        proposed_status=proposed.status,
        proposed_has_diagnosis_milestone=proposed.has_diagnosis_milestone,
        proposed_letter_inferred_benign=proposed.letter_inferred_benign,
    )
    if flip.flips and not request.confirm_bucket_flip:
        raise BucketFlipNotConfirmedError(flip)

    locks: list[VerificationLock] = []
    slot_index = {row.get("slot"): row for row in snapshot.slots}

    for action in request.actions:
        slot_row = slot_index.get(action.slot)
        if slot_row is None:
            raise UnknownSlotError(
                f"Action targets unknown slot {action.slot!r} on episode "
                f"{snapshot.episode_id!r}"
            )

        # Lock the IS_PART_OF edge representing the slot, even when
        # the slot is currently unfilled - the lock prevents the
        # rebuild guard from later attaching a fresh encounter to a
        # slot the reviewer already decided to leave empty or mark as
        # not-applicable.
        slot_encounter = (
            action.encounter_id
            if action.action == "replace"
            else slot_row.get("encounter_id")
        )
        entity_id = _slot_lock_id(snapshot.episode_id, slot_encounter)

        mutation = (
            mutation_factory(snapshot.episode_id, action, snapshot)
            if mutation_factory is not None
            else None
        )

        lock = apply_with_lock(
            lock_client,
            entity_type="is_part_of_edge",
            entity_id=entity_id,
            locked_by=request.reviewed_by,
            locked_by_role=request.reviewer_role,
            lock_reason=f"{action.action}: {request.reason}",
            source=source,
            mutation=mutation,
        )
        locks.append(lock)

    return ReconcileResult(
        episode_id=snapshot.episode_id,
        bucket=flip.proposed_bucket,
        flip=flip,
        locks=locks,
    )
