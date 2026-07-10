"""Admin endpoints for TRUD terminology sync.

Atlas trace:
  DO: DO-EC41233C (sync router)
  DO: DO-669D6A69 (terminology audit log)
  DI: DI-9D0DF618 (sync trigger/stream)
  DI: DI-2AD4CCC3 (audit log of admin actions)

GET  /admin/terminology/status        - TRUD package versions + Neo4j counts
GET  /admin/terminology/sync/stream   - SSE stream: download, extract, load
GET  /admin/terminology/audit-log     - Immutable audit log of admin actions

Ownership note (2026-07 CTO peer-review item 2: core-api router
decomposition -- "thin terminology ownership" follow-up): this router is
genuinely core-api-only admin policy (TRUD sync orchestration + audit
log) with no equivalent surface in terminology_api, so it needed no
changes. See services/api/app/routers/terminology.py for the ownership
note on the *other* terminology router, which does have real duplication
with terminology_api.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.deps import require_admin
from app.services.terminology_audit import (
    ACTION_SYNC_TRIGGER,
    get_entries,
    run_sync_with_audit,
    write_entry,
)
from app.services.trud_sync import PACKAGES, full_sync, get_status
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/terminology", tags=["admin", "terminology"])

EXTERNAL_CONTENT = Path(os.environ.get("EXTERNAL_CONTENT_DIR", "external_content"))


def _sse(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status")
def terminology_status(
    _: Annotated[CallerScope, Depends(require_admin)],
):
    """Return TRUD release versions and current Neo4j node counts."""
    return get_status(EXTERNAL_CONTENT)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@router.get("/audit-log")
def terminology_audit_log(
    scope: Annotated[CallerScope, Depends(require_admin)],
    since: Annotated[
        str | None, Query(description="ISO 8601 lower bound (inclusive)")
    ] = None,
    until: Annotated[
        str | None, Query(description="ISO 8601 upper bound (inclusive)")
    ] = None,
):
    """Return immutable audit entries for terminology administrator actions."""
    return {"entries": get_entries(since=since, until=until)}


# ---------------------------------------------------------------------------
# SSE sync stream
# ---------------------------------------------------------------------------


def _derive_phases(packages: list[str]) -> set[int]:
    """Auto-select loader phases from the requested package list."""
    phases: set[int] = set()
    for key in packages:
        if key in PACKAGES:
            phases |= PACKAGES[key]["phases"]
    return phases


def _run_sync_thread(
    user: str,
    packages: list[str],
    phases: set[int],
    events: "queue.Queue[dict | None]",
) -> None:
    run_sync_with_audit(user, packages, phases, events, full_sync, EXTERNAL_CONTENT)


def _event_generator(events: "queue.Queue[dict | None]"):
    while True:
        try:
            event = events.get(timeout=2.0)
        except queue.Empty:
            yield _sse("heartbeat", {"ts": time.time()})
            continue
        if event is None:
            break
        yield _sse(event.get("type", "log"), event)


@router.get("/sync/stream")
def terminology_sync_stream(
    scope: Annotated[CallerScope, Depends(require_admin)],
    packages: Annotated[
        str, Query(description="Comma-separated: snomed,dmd")
    ] = "snomed,dmd",
    phases: Annotated[
        str, Query(description="Comma-separated phase numbers, or 'auto'")
    ] = "auto",
):
    """Stream a TRUD download + Neo4j load as Server-Sent Events."""
    pkg_list = [p.strip() for p in packages.split(",") if p.strip()]
    if phases.strip() == "auto":
        phase_set = _derive_phases(pkg_list)
    else:
        phase_set = {int(p.strip()) for p in phases.split(",") if p.strip().isdigit()}

    user = getattr(scope, "email", "unknown")
    try:
        write_entry(
            user=user,
            action_type=ACTION_SYNC_TRIGGER,
            packages=pkg_list,
            outcome="in_progress",
            detail=f"phases={sorted(phase_set)}",
        )
    except Exception:
        logger.warning("audit: failed to write sync trigger entry", exc_info=True)

    events: queue.Queue[dict | None] = queue.Queue()
    threading.Thread(
        target=_run_sync_thread,
        args=(user, pkg_list, phase_set, events),
        daemon=True,
    ).start()

    return StreamingResponse(
        _event_generator(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
