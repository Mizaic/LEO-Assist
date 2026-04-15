"""Research job runner.

Executes algorithm missions in background threads.
Writes results back to the job store.
Publishes progress events to Redis pub/sub channel ``research:{job_id}``
so the SSE relay can stream them to the UI.

Architecture note: the runner imports the shared algorithm_runner from
the analytics_api service package.  In production, this is handled by
running the research worker container with the repo root on PYTHONPATH.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict

from services.research_worker.app.job_store import ResearchJob, ResearchJobStore

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = int(os.getenv("RESEARCH_MAX_CONCURRENT_JOBS", "3"))
_semaphore = threading.Semaphore(_MAX_CONCURRENT)


def submit_job(job: ResearchJob, store: ResearchJobStore) -> None:
    """Submit a research job to run in a daemon thread."""
    t = threading.Thread(
        target=_run_job,
        args=(job, store),
        daemon=True,
        name=f"research-job-{job.job_id[:12]}",
    )
    t.start()


def _run_job(job: ResearchJob, store: ResearchJobStore) -> None:
    """Execute a research mission -- runs in a background thread."""
    acquired = _semaphore.acquire(blocking=False)
    if not acquired:
        store.update(
            job,
            status="failed",
            error="Too many concurrent research jobs. Please try again shortly.",
            completed_at=time.time(),
        )
        _publish(job.job_id, {"type": "failed", "error": "Concurrency limit reached"})
        return

    store.update(job, status="running", started_at=time.time())
    _publish(job.job_id, {"type": "running", "job_id": job.job_id})
    try:
        result = _execute_mission(job)
        has_error = bool(result.get("error"))
        store.update(
            job,
            status="failed" if has_error else "done",
            completed_at=time.time(),
            result=result,
            error=result.get("error"),
        )
        event_type = "failed" if has_error else "done"
        _publish(
            job.job_id,
            {"type": event_type, "job_id": job.job_id, "status": event_type},
        )
    except Exception as exc:
        logger.error("Research job %s failed: %s", job.job_id, exc, exc_info=True)
        store.update(
            job,
            status="failed",
            completed_at=time.time(),
            error=str(exc),
        )
        _publish(job.job_id, {"type": "failed", "error": str(exc)})
    finally:
        _semaphore.release()


def _execute_mission(job: ResearchJob) -> Dict[str, Any]:
    """Execute the mission algorithm and return serialised result dict."""
    from libs.auth.org_scope import CallerScope
    from libs.neo4j_client.client import PatientGraphClient
    from services.analytics_api.app.services.algorithm_runner import run_mission
    from services.analytics_api.app.routers.research import _serialise_result

    scope = CallerScope(
        email="research-worker@internal",
        is_admin=job.is_admin,
        org_ids=job.org_ids,
    )
    client = PatientGraphClient()
    try:
        result = run_mission(
            mission_id=job.mission_id,
            client=client,
            scope=scope,
            area=job.area,
            period=job.period,
            detail=job.detail,
            patient_id=job.patient_id,
        )
        return _serialise_result(result)
    finally:
        client.close()


def _publish(job_id: str, payload: Dict[str, Any]) -> None:
    """Publish a progress event to the Redis pub/sub channel."""
    try:
        import redis as _redis

        from services.research_worker.app.job_store import REDIS_URL

        r = _redis.from_url(REDIS_URL)
        r.publish(f"research:{job_id}", json.dumps(payload, default=str))
    except Exception as exc:
        logger.warning("Failed to publish research event for %s: %s", job_id, exc)
