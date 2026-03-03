"""Admin endpoints for TRUD terminology sync.

GET  /admin/terminology/status        - TRUD package versions + Neo4j counts
GET  /admin/terminology/sync/stream   - SSE stream: download, extract, load
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
    packages: list[str],
    phases: set[int],
    events: "queue.Queue[dict | None]",
) -> None:
    def emit(event: dict) -> None:
        events.put(event)

    try:
        full_sync(EXTERNAL_CONTENT, packages, phases, emit)
    except Exception as exc:
        logger.exception("Unexpected error in TRUD sync thread")
        events.put({"type": "sync_error", "msg": str(exc)})
    finally:
        events.put(None)  # sentinel


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
    _: Annotated[CallerScope, Depends(require_admin)],
    packages: Annotated[str, Query(description="Comma-separated: snomed,dmd")] = "snomed,dmd",
    phases: Annotated[str, Query(description="Comma-separated phase numbers, or 'auto'")] = "auto",
):
    """Stream a TRUD download + Neo4j load as Server-Sent Events."""
    pkg_list = [p.strip() for p in packages.split(",") if p.strip()]
    if phases.strip() == "auto":
        phase_set = _derive_phases(pkg_list)
    else:
        phase_set = {int(p.strip()) for p in phases.split(",") if p.strip().isdigit()}

    events: queue.Queue[dict | None] = queue.Queue()
    threading.Thread(
        target=_run_sync_thread,
        args=(pkg_list, phase_set, events),
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
