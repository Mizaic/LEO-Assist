"""Background sweeper for stale ExtractionValidationRun rows.

Atlas trace:
  UN: UN-89E2AE36  (clinical extraction validation)
  DI: DI-1B3B5375  (validation runs surface clinician-reviewable F1)
  DI: DI-B492CAFD  (UI-triggered extraction validation run results)
  DO: DO-416BA91D  (extraction scenarios admin review and run surface)
  VT: VT-C9325761  (finalisation survives API restart and logout)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-1B3B5375")

A validation run goes through three external events that can strand it:

1. The API process exits or reloads while the daemon publish thread is still
   sending bus messages. publish_state stays "publishing"; published_count is
   less than case_count; no one will ever poll the run again on the new
   instance because in-memory state is lost.
2. The user closes the browser before the worker has emitted AuditEvents
   for every case. The parent run sits at status "running" forever because
   the poll endpoint is what drives finalisation.
3. The pipeline worker dies between message-consume and audit-write, leaving
   the parent run with partial audit rows and no chance of completion.
4. All bus messages were published but fewer AuditEvent rows arrive than
   cases (worker or queue stopped). After AUDIT_HARD_CUTOFF_SECONDS the
   sweeper marks the parent run failed so the UI is not stuck at 9/104.

This sweeper runs periodically on the API and, for each stale row, asks the
extraction_scenarios router to recover the run (rehydrate the in-memory
state and attempt finalisation from audit data). Rows that cannot recover
are marked failed with a human-readable reason so the UI surfaces something
useful instead of a phantom "running".
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


# How often the sweeper wakes up. Set short enough that a logged-out user
# returning 10 minutes later sees a finalised result, not a spinner.
SWEEP_INTERVAL_SECONDS = int(
    os.getenv("EXTRACTION_RUN_SWEEP_INTERVAL_SECONDS", "120")
)

# A run younger than RECOVERY_CUTOFF_SECONDS is left alone so the original
# request thread has time to finish publishing without interference.
RECOVERY_CUTOFF_SECONDS = int(
    os.getenv("EXTRACTION_RUN_RECOVERY_CUTOFF_SECONDS", "300")
)

# If publish_state stays "publishing" past PUBLISH_HARD_CUTOFF_SECONDS the
# publisher daemon thread is presumed dead (e.g. API process killed at
# logout). The sweeper force-fails the run so the UI moves on.
PUBLISH_HARD_CUTOFF_SECONDS = int(
    os.getenv("EXTRACTION_RUN_PUBLISH_HARD_CUTOFF_SECONDS", "900")
)

# If publish_state is "published" but AuditEvent rows never arrive for every
# child run, the coding worker or message bus likely stopped. Fail the parent
# run after this cutoff so it does not sit in "running" forever.
AUDIT_HARD_CUTOFF_SECONDS = int(
    os.getenv("EXTRACTION_RUN_AUDIT_HARD_CUTOFF_SECONDS", str(24 * 60 * 60))
)


def published_audit_incomplete_reason(
    row: dict[str, Any],
    now: datetime,
    *,
    read_audit_rows: Any,
) -> str | None:
    """Return a failure reason when a published run never finished auditing."""
    publish_state = str(row.get("publish_state") or "")
    if publish_state != "published":
        return None
    triggered = _parse_iso(row.get("triggered_at"))
    age_seconds = (now - triggered).total_seconds() if triggered else 0.0
    if age_seconds < AUDIT_HARD_CUTOFF_SECONDS:
        return None
    child_run_ids = list(row.get("child_run_ids") or [])
    case_count = int(row.get("case_count") or len(child_run_ids) or 0)
    if not child_run_ids or case_count <= 0:
        return None
    completed = len(read_audit_rows(child_run_ids))
    if completed >= case_count:
        return None
    return (
        f"pipeline returned {completed}/{case_count} case audit rows "
        f"after {int(age_seconds)}s; workers likely stopped or "
        f"messages were not processed"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sweep_once() -> dict[str, int]:
    """Inspect stale validation runs once and return a counter summary.

    Returns a dict with keys: scanned, recovered, finalised, failed. The
    counts are useful for tests and for logging so we can see at-a-glance
    whether the sweeper is doing its job.
    """
    from libs.cypher.extraction_scenario_queries import FIND_STALE_VALIDATION_RUNS
    from app.db.neo4j_client import CodingGraphClient
    from app.routers import extraction_scenarios

    cutoff_at = (_utc_now() - timedelta(seconds=RECOVERY_CUTOFF_SECONDS)).isoformat()
    client = CodingGraphClient()
    try:
        stale_rows = client.run(FIND_STALE_VALIDATION_RUNS, cutoff_at=cutoff_at)
    finally:
        client.close()

    summary = {"scanned": 0, "recovered": 0, "finalised": 0, "failed": 0}
    now = _utc_now()
    for raw in stale_rows or []:
        summary["scanned"] += 1
        _sweep_row(dict(raw), now, extraction_scenarios, summary)
    if summary["scanned"]:
        logger.info("ExtractionRun sweep: %s", summary)
    return summary


def _sweep_row(
    row: dict[str, Any],
    now: datetime,
    extraction_scenarios: Any,
    summary: dict[str, int],
) -> None:
    """Process a single stale run row.

    Three outcomes:

    * Hard cutoff exceeded with publish_state still "publishing": mark failed
      so the UI is not stuck on a row whose publisher daemon thread has died.
    * Otherwise call the router's recovery path which either finalises from
      audit rows or updates in-memory progress for the next sweep.
    """
    run_id = str(row.get("run_id") or "")
    if not run_id:
        return

    triggered = _parse_iso(row.get("triggered_at"))
    age_seconds = (now - triggered).total_seconds() if triggered else 0.0
    publish_state = str(row.get("publish_state") or "")

    if (
        publish_state == "publishing"
        and age_seconds >= PUBLISH_HARD_CUTOFF_SECONDS
    ):
        published_count = int(row.get("published_count") or 0)
        case_count = int(row.get("case_count") or 0)
        reason = (
            f"publish loop did not complete ({published_count}/{case_count} "
            f"messages sent in {int(age_seconds)}s); the API process or its "
            f"daemon thread likely exited mid-publish"
        )
        extraction_scenarios._fail_unrecoverable_run(run_id, row, reason=reason)
        summary["failed"] += 1
        return

    audit_reason = published_audit_incomplete_reason(
        row,
        now,
        read_audit_rows=extraction_scenarios._read_validation_audit_rows,
    )
    if audit_reason:
        extraction_scenarios._fail_unrecoverable_run(
            run_id, row, reason=audit_reason
        )
        summary["failed"] += 1
        return

    try:
        recovered = extraction_scenarios._recover_running_run(run_id, row)
    except Exception:
        logger.exception("ExtractionRun sweep: recovery failed run_id=%s", run_id)
        return

    summary["recovered"] += 1
    if str(recovered.get("status")) == "completed":
        summary["finalised"] += 1
    elif str(recovered.get("status")) == "failed":
        summary["failed"] += 1


async def run_sweeper_loop() -> None:
    """Run sweep_once() on a fixed interval until cancelled."""
    logger.info(
        "ExtractionRun sweeper started: interval=%ss recovery_cutoff=%ss "
        "publish_hard_cutoff=%ss audit_hard_cutoff=%ss",
        SWEEP_INTERVAL_SECONDS,
        RECOVERY_CUTOFF_SECONDS,
        PUBLISH_HARD_CUTOFF_SECONDS,
        AUDIT_HARD_CUTOFF_SECONDS,
    )
    while True:
        try:
            await asyncio.to_thread(sweep_once)
        except Exception:
            logger.exception("ExtractionRun sweeper iteration raised")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
