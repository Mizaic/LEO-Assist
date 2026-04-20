"""Verification-lock guard for the episode builder rebuild path.

A reviewer who confirms a milestone slot, an encounter, an IS_PART_OF
edge, or a coded link in the Reconcile Pathway drawer writes a
:VerificationLock node via libs.locks.lock_service. The deterministic
episode builder rebuilds the pathway on every patient analysis run, so
without a guard the rebuild would silently overwrite human-confirmed
state.

This module provides three primitives consumed by ``build_episodes``
and ``_link_encounters_to_episode``:

* ``load_lock_state``        -- one read per patient at the start of a
  build, returning a structured snapshot of the locks attached to that
  patient's encounters and episodes.
* ``is_episode_fully_locked`` -- True when ``entity_type='episode'``
  with ``entity_id=<episode_id>`` is locked. Used to skip the entire
  episode build (no MERGE_EPISODE, no LINK_ENCOUNTERS).
* ``filter_link_groups``     -- removes any (encounter, milestone)
  pair whose IS_PART_OF edge is locked, so the rebuild path never
  rewrites a locked edge with a different milestone_type.

The companion helper ``locked_anchors_for_episode`` returns the
locked encounter ids by milestone, suitable for embedding into the
LLM prompt's ``fixed_milestones`` block (libs.prompts.episode_builder_v1).

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from libs.locks import VerificationLock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EpisodeLockState:
    """All locks visible to one patient build, indexed for fast lookups.

    ``locked_episode_ids`` -- episode ids with a direct ``episode`` lock.
    ``locked_encounter_ids`` -- encounter ids with a direct ``encounter`` lock.
    ``locked_is_part_of_keys`` -- ``"<encounter_id>:<episode_id>"`` keys for
        locked IS_PART_OF edges.
    ``locked_coded_link_keys`` -- ``"<encounter_id>:<concept_id>"`` keys.
    ``locks`` -- the full list (kept for audit/log surfacing).
    """

    locked_episode_ids: frozenset[str] = frozenset()
    locked_encounter_ids: frozenset[str] = frozenset()
    locked_is_part_of_keys: frozenset[str] = frozenset()
    locked_coded_link_keys: frozenset[str] = frozenset()
    locks: tuple[VerificationLock, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not (
            self.locked_episode_ids
            or self.locked_encounter_ids
            or self.locked_is_part_of_keys
            or self.locked_coded_link_keys
        )


def _is_part_of_key(encounter_id: str, episode_id: str) -> str:
    return f"{encounter_id}:{episode_id}"


def load_lock_state(patient_id: str, lock_client: Any) -> EpisodeLockState:
    """Read every lock attached to this patient's graph neighbourhood.

    ``lock_client`` follows the libs.locks._Client protocol (anything
    with a ``session()`` method that returns a Neo4j-style session).
    Failures here are non-fatal -- the rebuild guard degrades to
    "unlocked" rather than blocking a routine pipeline run.
    """
    try:
        from libs.locks import list_locks_for_patient

        locks = list_locks_for_patient(lock_client, patient_id=patient_id)
    except Exception:  # noqa: BLE001 -- degradation only
        logger.exception(
            "lock_guard: failed to load locks for patient %s; treating as unlocked",
            patient_id,
        )
        return EpisodeLockState()

    return _build_state(tuple(locks))


def _build_state(locks: tuple[VerificationLock, ...]) -> EpisodeLockState:
    episode_ids: set[str] = set()
    encounter_ids: set[str] = set()
    edge_keys: set[str] = set()
    link_keys: set[str] = set()
    for lock in locks:
        if lock.entity_type == "episode":
            episode_ids.add(lock.entity_id)
        elif lock.entity_type == "encounter":
            encounter_ids.add(lock.entity_id)
        elif lock.entity_type == "is_part_of_edge":
            edge_keys.add(lock.entity_id)
        elif lock.entity_type == "coded_link":
            link_keys.add(lock.entity_id)
        # 'assertion' locks are NOT consulted by the rebuild path --
        # they are honoured by the recode pipeline (libs/cypher/
        # documents_queries.py) which short-circuits on locked links.
    return EpisodeLockState(
        locked_episode_ids=frozenset(episode_ids),
        locked_encounter_ids=frozenset(encounter_ids),
        locked_is_part_of_keys=frozenset(edge_keys),
        locked_coded_link_keys=frozenset(link_keys),
        locks=locks,
    )


def is_episode_fully_locked(episode_id: str, lock_state: EpisodeLockState) -> bool:
    """True when ``entity_type='episode'`` is locked for this episode.

    Episode-level locks are an explicit reviewer signal that the episode's
    milestone topology is final. An encounter-level lock alone is NOT a
    full episode lock -- the reviewer may still want the builder to add
    new milestones (e.g. a future treatment_started) around it.
    """
    return episode_id in lock_state.locked_episode_ids


def filter_link_groups(
    link_groups: list[tuple[list[dict[str, Any]], str]],
    *,
    episode_id: str,
    lock_state: EpisodeLockState,
) -> list[tuple[list[dict[str, Any]], str]]:
    """Drop encounters whose IS_PART_OF edge is locked from rebuild groups.

    The LINK_ENCOUNTERS Cypher deletes every existing IS_PART_OF edge
    for the episode and re-creates them from the supplied list. If we
    let a locked edge participate in that delete-and-recreate cycle the
    edge would be transiently dropped (breaking lock semantics) or
    rewritten with a different ``milestone_type`` (silently corrupting
    a confirmed slot). The cleanest fix is to remove locked
    encounter ids from the rebuild input entirely so the existing
    locked edge is preserved by the OPTIONAL MATCH ... WHERE NOT locked
    clause in the modified LINK_ENCOUNTERS query (see _cypher.py).
    """
    if lock_state.is_empty():
        return link_groups

    filtered: list[tuple[list[dict[str, Any]], str]] = []
    for anchor_list, milestone_type in link_groups:
        kept: list[dict[str, Any]] = []
        for anchor in anchor_list:
            eid = str(anchor.get("encounter_id") or "")
            if not eid:
                kept.append(anchor)
                continue
            edge_key = _is_part_of_key(eid, episode_id)
            if edge_key in lock_state.locked_is_part_of_keys:
                # The locked edge already exists with the reviewer's
                # chosen milestone_type. Skip it on this rebuild pass.
                continue
            if eid in lock_state.locked_encounter_ids:
                # A locked encounter is allowed to be re-linked to the
                # episode but not stripped of any milestone -- so we keep
                # it. The Cypher guard below ensures the locked edges
                # cannot be deleted.
                pass
            kept.append(anchor)
        if kept:
            filtered.append((kept, milestone_type))
    return filtered


def locked_anchors_for_episode(
    episode_id: str,
    lock_state: EpisodeLockState,
) -> dict[str, list[str]]:
    """Return ``{milestone_type: [encounter_id, ...]}`` for locked edges.

    Consumed by the LLM prompt builder (``libs.prompts.episode_builder_v1``)
    to populate the ``fixed_milestones`` block that tells the model
    which slots are reviewer-confirmed and must not be replaced.
    Milestone type is encoded in the IS_PART_OF edge, not on the lock,
    so we expose the raw encounter ids and the consumer can look up
    the slot from the live graph.
    """
    out: dict[str, list[str]] = {}
    for lock in lock_state.locks:
        if lock.entity_type != "is_part_of_edge":
            continue
        if not lock.entity_id.endswith(":" + episode_id):
            continue
        encounter_id = lock.entity_id[: -(len(episode_id) + 1)]
        if not encounter_id:
            continue
        # We do not know the milestone_type from the lock alone; the
        # caller is expected to enrich with the live graph. Index by
        # 'locked' as a placeholder so the prompt at least lists the
        # encounters; downstream resolution adds the specific slot.
        out.setdefault("locked", []).append(encounter_id)
    return out
