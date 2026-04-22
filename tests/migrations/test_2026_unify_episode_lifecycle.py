"""VT-66DA36EC: 2026_unify_episode_lifecycle migration parity.

Pins the dry-run / commit shape of the lifecycle unification
migration so a regression cannot make the migration:

* skip an unreviewed legacy status,
* overwrite a status protected by ``reviewed_at IS NOT NULL``,
* leave the two parallel review-flag fields out of lockstep, or
* introduce a non-canonical status spelling.

Atlas trace:
  DI: DI-C4CEFA32
  DO: DO-C5B5E91E
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from libs.episodes.status import EpisodeStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "migrations"
    / "2026_unify_episode_lifecycle.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_unify_episode_lifecycle", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_status_rewrites_only_target_canonical_values() -> None:
    """Every rewrite target MUST be a canonical EpisodeStatus value
    so the migration cannot reintroduce a free-text status string."""
    mod = _load_module()
    legal = {s.value for s in EpisodeStatus}
    for legacy, canonical in mod._STATUS_REWRITES.items():
        assert canonical in legal, (
            f"rewrite target {canonical!r} for {legacy!r} not in EpisodeStatus"
        )


def test_status_rewrites_cover_v2_and_manual_create_drift() -> None:
    """The migration MUST cover the four legacy spellings shipped to
    production: in_review (manual create default), open / closed /
    benign_closure (v2 detector boundary)."""
    mod = _load_module()
    expected_legacy = {
        "in_review": EpisodeStatus.REVIEW.value,
        "open": EpisodeStatus.ACTIVE.value,
        "closed": EpisodeStatus.COMPLETED.value,
        "benign_closure": EpisodeStatus.CLOSED_BENIGN.value,
    }
    for legacy, canonical in expected_legacy.items():
        assert mod._STATUS_REWRITES.get(legacy) == canonical


def test_rewrite_status_q_skips_reviewed_episodes() -> None:
    """The status rewrite MUST be guarded by reviewed_at IS NULL so
    a curator-signed verdict is never silently overwritten."""
    mod = _load_module()
    assert "ep.reviewed_at IS NULL" in mod._REWRITE_STATUS_Q


def test_flag_backfill_uses_logical_or() -> None:
    """The review-flag backfill must use a logical OR so an episode
    that was flagged in one field is flagged in both -- never the
    reverse (clearing a flag silently)."""
    mod = _load_module()
    body = mod._FLAG_BACKFILL_Q
    # OR between needs_review and needs_human_review.
    assert "OR coalesce(ep.needs_human_review" in body
    assert "ep.needs_review = unified" in body
    assert "ep.needs_human_review = unified" in body


def test_dry_run_does_not_call_rewrite_query() -> None:
    """Dry-run mode (commit=False) MUST count rows but NEVER execute
    the SET that rewrites status."""
    mod = _load_module()

    queries: list[str] = []

    def fake_run(query: str, **kwargs):
        queries.append(query)
        if query is mod._COUNT_STATUS_Q:
            return [{"n": 3}]
        if query is mod._REWRITE_STATUS_REVIEWED_Q:
            return [{"n": 1}]
        if query is mod._FLAG_DRIFT_Q:
            return [{"n": 0}]
        if query is mod._INVALID_Q:
            return []
        # Any other query in dry-run is unexpected.
        return []

    client = MagicMock()
    client.run.side_effect = fake_run

    status_changes, reviewed_skips = mod._rewrite_statuses(client, commit=False)

    # Dry-run reports 3-1=2 eligible per legacy bucket * 5 legacy keys = 10
    assert status_changes == 2 * len(mod._STATUS_REWRITES)
    assert reviewed_skips == 1 * len(mod._STATUS_REWRITES)
    # The rewrite query must NEVER appear in dry-run.
    assert all(q is not mod._REWRITE_STATUS_Q for q in queries), (
        "dry-run must not run _REWRITE_STATUS_Q"
    )


def test_commit_runs_rewrite_query_per_legacy_bucket() -> None:
    """Commit mode applies the rewrite for each legacy spelling that
    has at least one row, returning the changed count."""
    mod = _load_module()

    rewrite_calls: list[tuple[str, str]] = []

    def fake_run(query: str, **kwargs):
        if query is mod._COUNT_STATUS_Q:
            # All five legacy keys have one row each.
            return [{"n": 1}]
        if query is mod._REWRITE_STATUS_REVIEWED_Q:
            return [{"n": 0}]
        if query is mod._REWRITE_STATUS_Q:
            rewrite_calls.append((kwargs["legacy"], kwargs["canonical"]))
            return [{"n": 1}]
        if query is mod._FLAG_DRIFT_Q:
            return [{"n": 0}]
        if query is mod._INVALID_Q:
            return []
        return []

    client = MagicMock()
    client.run.side_effect = fake_run

    changes, reviewed = mod._rewrite_statuses(client, commit=True)

    assert changes == len(mod._STATUS_REWRITES)
    assert reviewed == 0
    legacy_called = {legacy for legacy, _ in rewrite_calls}
    assert legacy_called == set(mod._STATUS_REWRITES.keys())
    for legacy, canonical in rewrite_calls:
        assert mod._STATUS_REWRITES[legacy] == canonical
