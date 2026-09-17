"""A run that still says running but holds no live lease is failed.

Quiet extract jobs kept showing as running after the worker died.
That hid the failure from clinicians.

Atlas:
  DI: DI-36F80B95
  DO: DO-CE65B1F2
  VT: VT-0203C659
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.cypher.fail_stale_run_queries import FAIL_STALE_RUNNING_PIPELINE_RUNS
from libs.workflow.fail_stale_runs import fail_stale_running_runs, is_stale_running_run


_NOW = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)


def test_expired_lease_and_old_update_is_stale() -> None:
    assert (
        is_stale_running_run(
            run_status="running",
            run_updated_at=_NOW - timedelta(hours=2),
            now=_NOW,
            live_lease_untils=[_NOW - timedelta(hours=1)],
        )
        is True
    )


def test_live_lease_is_not_stale() -> None:
    assert (
        is_stale_running_run(
            run_status="running",
            run_updated_at=_NOW - timedelta(hours=2),
            now=_NOW,
            live_lease_untils=[_NOW + timedelta(minutes=10)],
        )
        is False
    )


def test_recent_handoff_without_lease_is_not_stale() -> None:
    assert (
        is_stale_running_run(
            run_status="running",
            run_updated_at=_NOW - timedelta(minutes=2),
            now=_NOW,
            live_lease_untils=[],
        )
        is False
    )


def test_old_running_run_with_no_lease_is_stale() -> None:
    assert (
        is_stale_running_run(
            run_status="running",
            run_updated_at=_NOW - timedelta(hours=3),
            now=_NOW,
            live_lease_untils=[],
        )
        is True
    )


def test_completed_run_is_not_stale() -> None:
    assert (
        is_stale_running_run(
            run_status="completed",
            run_updated_at=_NOW - timedelta(hours=3),
            now=_NOW,
            live_lease_untils=[],
        )
        is False
    )


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params: object) -> list[dict]:
        self.calls.append((query, params))
        return [{"run_ids": ["run-quiet-1", "run-quiet-2"]}]


def test_fail_stale_running_runs_writes_failed_status() -> None:
    client = _FakeClient()
    changed = fail_stale_running_runs(client, stale_after_minutes=10)
    assert changed == ["run-quiet-1", "run-quiet-2"]
    query, params = client.calls[0]
    assert query == FAIL_STALE_RUNNING_PIPELINE_RUNS
    assert params["stale_after_minutes"] == 10
    assert "stale_running_no_active_lease" in str(params["errors_json"])
