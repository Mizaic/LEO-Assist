"""NICE guideline ingestion endpoints.

Provides:
  GET  /nice/catalogue?q=   -- searchable guideline index (Redis-cached)
  POST /nice/ingest         -- fire-and-track ingest by NICE code
  GET  /nice/events         -- SSE progress stream for a job
  GET  /nice/jobs/{job_id}/status
  GET  /nice/jobs

All endpoints require the ai.admin role.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.deps import require_admin
from app.services.nice_api_client import NICE_CODE_RE, NiceApiClient
from app.services.nice_graph_upserter import NiceGraphUpserter
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["nice-guidance"])

_jobs: dict[str, dict[str, Any]] = {}
_queues: dict[str, queue.Queue] = {}
_IDLE_TIMEOUT = 300


class NiceIngestRequest(BaseModel):
    """Request body for POST /nice/ingest."""

    code: str

    @property
    def validated_code(self) -> str:
        """Return upper-cased code; raises ValueError for non-NICE codes."""
        upper = self.code.strip().upper()
        if not NICE_CODE_RE.match(upper):
            raise ValueError(
                f"'{self.code}' is not a valid NICE guidance code. "
                "Expected format: NG151, CG89, TA123, QS12, etc."
            )
        return upper


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _emit(job_id: str, event: str, data: dict) -> None:
    q = _queues.get(job_id)
    if q:
        q.put(_sse(event, data))
    _jobs.get(job_id, {}).update(data)


@router.get("/nice/catalogue")
async def get_catalogue(
    q: str = Query(default="", min_length=0),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Search the NICE guideline catalogue by keyword or condition name.

    When a query is provided, searches the live NICE guidance index API
    (supports condition name, topic, or NICE code). Falls back to the
    Redis-cached list of previously loaded guidelines on API failure.
    When no query is provided, returns recently loaded guidelines from cache.
    """
    client = NiceApiClient()
    if not q:
        entries = await client.fetch_catalogue()
        return entries[:20]

    # Try live NICE index search first (supports condition name e.g. "cancer")
    results = await client.search_index(q)
    if results:
        return results

    # Fall back to Redis cache filter if NICE API unavailable
    entries = await client.fetch_catalogue()
    q_lower = q.lower()
    matches = [
        e for e in entries
        if q_lower in e.get("title", "").lower()
        or q_lower in e.get("code", "").lower()
    ]
    return matches[:20]


@router.post("/nice/catalogue/sync", status_code=202)
async def sync_catalogue(
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Sync the full NICE guidance index into the Redis catalogue.

    Walks every page of the NICE guidance index and replaces the local Redis
    catalogue so the admin search autocomplete works from day one without
    requiring guidelines to be individually ingested first.

    The sync runs in the background. Check ``GET /nice/catalogue/sync/status``
    to see when it completes.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "code": "__catalogue_sync__",
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error": None,
    }

    def _run_sync() -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            count = loop.run_until_complete(NiceApiClient().sync_catalogue_from_index())
            _jobs[job_id].update({
                "status": "done",
                "recommendations": count,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.exception("Catalogue sync failed: %s", exc)
            _jobs[job_id].update({"status": "error", "error": str(exc)})
        finally:
            loop.close()

    threading.Thread(target=_run_sync, daemon=True).start()
    return {"job_id": job_id}


@router.post("/nice/ingest", status_code=202)
async def ingest_guideline(
    req: NiceIngestRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Trigger ingest of a NICE guideline by code.

    The job runs in the background. Use GET /nice/events?job_id=
    to stream progress, or GET /nice/jobs/{job_id}/status to poll.
    """
    try:
        code = req.validated_code
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "code": code,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error": None,
    }
    _queues[job_id] = queue.Queue()
    thread = threading.Thread(
        target=_run_ingest,
        args=(job_id, code),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@router.get("/nice/events")
async def stream_events(
    job_id: str = Query(...),
    scope: CallerScope = Depends(require_admin),
) -> StreamingResponse:
    """Stream SSE progress events for an ingest job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    def _generate():
        q = _queues.get(job_id)
        if not q:
            yield _sse("error", {"message": "No event queue for job"})
            return
        yield _sse("connected", {"job_id": job_id})
        idle = 0
        while idle < _IDLE_TIMEOUT:
            try:
                msg = q.get(timeout=1)
                yield msg
                idle = 0
                if '"done"' in msg or '"error"' in msg:
                    break
            except queue.Empty:
                idle += 1

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/nice/jobs/{job_id}/status")
def get_job_status(
    job_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Return current status of an ingest job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/nice/jobs")
def list_jobs(scope: CallerScope = Depends(require_admin)) -> list[dict]:
    """List all active and recently completed ingest jobs."""
    return list(_jobs.values())


def _run_ingest(job_id: str, code: str) -> None:
    """Background thread: fetch from NICE API and upsert to Neo4j."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_ingest(job_id, code))
    except Exception as exc:
        logger.exception("Ingest failed for %s: %s", code, exc)
        _emit(job_id, "error", {"status": "error", "error": str(exc)})
    finally:
        loop.close()


async def _async_ingest(job_id: str, code: str) -> None:
    """Async ingest steps for a single NICE guideline."""
    _emit(job_id, "progress", {"status": "running", "step": "Fetching guideline..."})
    client = NiceApiClient()
    upserter = NiceGraphUpserter()

    guidance = await client.get_guidance(code)
    _emit(job_id, "progress", {"step": "Saving guideline..."})
    guideline_id = upserter.upsert_guideline(guidance)

    _emit(job_id, "progress", {"step": "Fetching recommendations..."})
    recommendations = await client.get_recommendations(code)
    for idx, rec in enumerate(recommendations):
        rec_id = f"{guideline_id}:R{idx:03d}"
        upserter.upsert_recommendation(guideline_id, rec_id, rec)

    _emit(job_id, "progress", {"step": "Fetching chapters..."})
    chapters = await client.get_chapters(code)
    for idx, chapter in enumerate(chapters):
        upserter.upsert_section(guideline_id, chapter, idx)

    title = guidance.get("Title", code)
    guidance_type = guidance.get("Type", "clinical-guideline")
    await client.add_to_catalogue(code, title, guidance_type)

    _emit(job_id, "done", {
        "status": "done",
        "step": "Complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_count": len(recommendations),
        "section_count": len(chapters),
    })
