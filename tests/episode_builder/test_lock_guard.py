"""Tests for the episode-builder VerificationLock rebuild guard.

Covers DI-C424BB44 / VT-96455BC1:

  - load_lock_state degrades to an empty state when the client raises
  - is_episode_fully_locked is True only for an explicit episode lock
  - filter_link_groups drops encounters whose IS_PART_OF edge is locked
  - filter_link_groups keeps unlocked anchors and anchors with empty ids
  - locked_anchors_for_episode reports locked encounters per episode
  - LINK_ENCOUNTERS Cypher protects locked edges in the delete pass
  - _link_encounters_to_episode forwards locked_encounter_ids to Cypher
  - The episode_builder_v1 task prompt declares a fixed_milestones slot
"""

from __future__ import annotations

from typing import Any

from libs.locks import VerificationLock
from services.analysis_worker.app.analyzers.episode_builder._cypher import (
    LINK_ENCOUNTERS,
)
from services.analysis_worker.app.analyzers.episode_builder._lock_guard import (
    EpisodeLockState,
    filter_link_groups,
    is_episode_fully_locked,
    load_lock_state,
    locked_anchors_for_episode,
)
from services.analysis_worker.app.analyzers.episode_builder._persistence import (
    _link_encounters_to_episode,
)


def _make_lock(
    *,
    entity_type: str,
    entity_id: str,
    lock_id: str = "lock-aaaaaaaa",
) -> VerificationLock:
    return VerificationLock(
        lock_id=lock_id,
        entity_type=entity_type,
        entity_id=entity_id,
        locked_by="alice@example.org",
        locked_by_role="clinician",
        lock_reason="confirmed",
        source="reconcile_pathway",
        locked_at="2026-04-20T00:00:00Z",
        updated_at="2026-04-20T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# load_lock_state
# ---------------------------------------------------------------------------


def test_load_lock_state_returns_empty_when_client_raises() -> None:
    class _BoomClient:
        def session(self):
            raise RuntimeError("neo4j down")

    state = load_lock_state("pat-1", _BoomClient())
    assert state.is_empty()
    assert state.locks == ()


# ---------------------------------------------------------------------------
# is_episode_fully_locked
# ---------------------------------------------------------------------------


def test_is_episode_fully_locked_only_for_episode_locks() -> None:
    state = EpisodeLockState(
        locked_episode_ids=frozenset({"ep-1"}),
        locked_encounter_ids=frozenset({"enc-1"}),
    )
    assert is_episode_fully_locked("ep-1", state) is True
    # Encounter-level locks alone are not enough to skip the rebuild.
    assert is_episode_fully_locked("ep-2", state) is False


# ---------------------------------------------------------------------------
# filter_link_groups
# ---------------------------------------------------------------------------


def test_filter_link_groups_drops_locked_edge_anchors() -> None:
    state = EpisodeLockState(
        locked_is_part_of_keys=frozenset({"enc-1:ep-1"}),
    )
    groups = [
        (
            [
                {"encounter_id": "enc-1"},
                {"encounter_id": "enc-2"},
            ],
            "referral",
        ),
        (
            [{"encounter_id": "enc-3"}],
            "diagnosis",
        ),
    ]
    out = filter_link_groups(groups, episode_id="ep-1", lock_state=state)
    # enc-1 dropped (locked edge); enc-2 kept; diagnosis group untouched.
    assert out == [
        ([{"encounter_id": "enc-2"}], "referral"),
        ([{"encounter_id": "enc-3"}], "diagnosis"),
    ]


def test_filter_link_groups_keeps_anchors_without_encounter_id() -> None:
    state = EpisodeLockState(
        locked_is_part_of_keys=frozenset({"enc-1:ep-1"}),
    )
    groups = [([{"encounter_id": ""}, {"foo": "bar"}], "first_presentation")]
    out = filter_link_groups(groups, episode_id="ep-1", lock_state=state)
    assert out == groups


def test_filter_link_groups_no_locks_returns_input_unchanged() -> None:
    state = EpisodeLockState()
    groups = [([{"encounter_id": "enc-1"}], "referral")]
    out = filter_link_groups(groups, episode_id="ep-1", lock_state=state)
    assert out is groups


def test_filter_link_groups_drops_only_for_target_episode() -> None:
    state = EpisodeLockState(
        locked_is_part_of_keys=frozenset({"enc-1:ep-1"}),
    )
    # enc-1 is locked against ep-1, NOT ep-2 -- ep-2 rebuild keeps it.
    groups = [([{"encounter_id": "enc-1"}], "referral")]
    out = filter_link_groups(groups, episode_id="ep-2", lock_state=state)
    assert out == groups


# ---------------------------------------------------------------------------
# locked_anchors_for_episode
# ---------------------------------------------------------------------------


def test_locked_anchors_for_episode_extracts_encounter_ids() -> None:
    locks = (
        _make_lock(
            entity_type="is_part_of_edge",
            entity_id="enc-1:ep-1",
            lock_id="lock-aaaaaaaa1",
        ),
        _make_lock(
            entity_type="is_part_of_edge",
            entity_id="enc-2:ep-1",
            lock_id="lock-aaaaaaaa2",
        ),
        _make_lock(
            entity_type="is_part_of_edge",
            entity_id="enc-3:ep-other",
            lock_id="lock-aaaaaaaa3",
        ),
        _make_lock(
            entity_type="encounter",
            entity_id="enc-9",
            lock_id="lock-aaaaaaaa4",
        ),
    )
    state = EpisodeLockState(locks=locks)
    out = locked_anchors_for_episode("ep-1", state)
    assert sorted(out["locked"]) == ["enc-1", "enc-2"]


# ---------------------------------------------------------------------------
# LINK_ENCOUNTERS Cypher invariants
# ---------------------------------------------------------------------------


def test_link_encounters_query_protects_locked_edges() -> None:
    # The rebuild guard depends on the WHERE NOT clause -- if it is ever
    # removed the entire DI-C424BB44 invariant collapses.
    assert "$locked_encounter_ids" in LINK_ENCOUNTERS
    assert "WHERE NOT enc_old.id IN" in LINK_ENCOUNTERS


def test_link_encounters_to_episode_passes_locked_ids() -> None:
    captured: dict[str, Any] = {}

    class _RecordingClient:
        def run(self, query: str, **kwargs: Any) -> list:
            captured["query"] = query
            captured["kwargs"] = kwargs
            return []

    state = EpisodeLockState(
        locked_is_part_of_keys=frozenset({"enc-locked:ep-7", "enc-other:ep-99"}),
    )
    _link_encounters_to_episode(
        _RecordingClient(),
        "ep-7",
        [([{"encounter_id": "enc-new"}], "referral")],
        lock_state=state,
    )
    assert captured["kwargs"]["episode_id"] == "ep-7"
    # Only the lock for THIS episode is forwarded; ep-99 is filtered out.
    assert captured["kwargs"]["locked_encounter_ids"] == ["enc-locked"]
    assert captured["kwargs"]["encounters"] == [
        {
            "encounter_id": "enc-new",
            "milestone_type": "referral",
            "referral_subtype": "",
        }
    ]


def test_link_encounters_to_episode_emits_empty_locked_list_without_state() -> None:
    captured: dict[str, Any] = {}

    class _RecordingClient:
        def run(self, query: str, **kwargs: Any) -> list:
            captured["kwargs"] = kwargs
            return []

    _link_encounters_to_episode(
        _RecordingClient(),
        "ep-7",
        [([{"encounter_id": "enc-1"}], "referral")],
    )
    # Default path still supplies the parameter so the Cypher coalesce
    # branch does not have to handle a missing key.
    assert captured["kwargs"]["locked_encounter_ids"] == []


# ---------------------------------------------------------------------------
# Prompt invariant (DI-C424BB44 LLM contract)
# ---------------------------------------------------------------------------


def test_episode_builder_prompt_declares_fixed_milestones_block() -> None:
    from libs.prompts.episode_builder_v1 import EPISODE_BUILDER_TASK_V1

    assert "{fixed_milestones}" in EPISODE_BUILDER_TASK_V1
    assert "Reviewer-confirmed milestones" in EPISODE_BUILDER_TASK_V1
    assert "LOCKED" in EPISODE_BUILDER_TASK_V1
