"""Mark quiet running pipeline jobs as failed.

A run that still says running but holds no live lease is not
running. Leaving it open hides the failure.

Atlas trace:
  DI: DI-36F80B95
  DO: DO-CE65B1F2
  VT: VT-0203C659
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from libs.cypher.fail_stale_run_queries import FAIL_STALE_RUNNING_PIPELINE_RUNS

_STALE_AFTER = timedelta(minutes=10)
_ERROR_JSON = '["stale_running_no_active_lease"]'


class _CypherClient(Protocol):
    def run(self, query: str, **params: Any) -> list[dict[str, Any]]: ...


def is_stale_running_run(
    *,
    run_status: str,
    run_updated_at: datetime,
    now: datetime,
    live_lease_untils: list[datetime | None],
    stale_after: timedelta = _STALE_AFTER,
) -> bool:
    """True when a running run is old and no stage still holds a lease."""
    if run_status != "running":
        return False
    if now - run_updated_at < stale_after:
        return False
    return not any(lease is not None and lease > now for lease in live_lease_untils)


def fail_stale_running_runs(
    client: _CypherClient,
    *,
    stale_after_minutes: int = 10,
) -> list[str]:
    """Fail every stale running run. Return the run ids that changed."""
    rows = client.run(
        FAIL_STALE_RUNNING_PIPELINE_RUNS,
        stale_after_minutes=max(1, stale_after_minutes),
        errors_json=_ERROR_JSON,
    )
    row = (rows or [{}])[0] if rows else {}
    return [str(run_id) for run_id in (row.get("run_ids") or []) if run_id]
