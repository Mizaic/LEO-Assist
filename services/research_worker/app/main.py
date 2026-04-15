"""Research Worker service.

Always-on FastAPI service (port 8007) that executes Pathway Explorer
algorithm missions as background jobs.

Routes
------
POST /research/jobs              -- submit a research mission run
GET  /research/jobs              -- list recent jobs
GET  /research/jobs/{job_id}     -- job detail + result
DELETE /research/jobs/{job_id}   -- cancel a queued job
GET  /research/progress/{job_id} -- SSE relay from Redis pub/sub
GET  /health                     -- service health check
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

import json  # noqa: E402
import logging  # noqa: E402
import queue  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import uvicorn  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from typing import Any, List, Optional  # noqa: E402

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from libs.auth.service_auth import verify_service_token  # noqa: E402
from libs.utils.logging import configure_logging  # noqa: E402

from services.research_worker.app.job_store import REDIS_URL, get_store  # noqa: E402
from services.research_worker.app.job_runner import submit_job  # noqa: E402

configure_logging(service_name="research-worker")
logger = logging.getLogger(__name__)

_IDLE_TIMEOUT_S = 300


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Research Worker starting on port 8007")
    yield
    logger.info("Research Worker shutting down")


app = FastAPI(
    title="Research Worker",
    version="1.0.0",
    description=(
        "Executes Pathway Explorer graph algorithm missions. "
        "Reads patient data from Neo4j via GDS, stores results, "
        "and streams progress to the UI via SSE."
    ),
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Request models -----------------------------------------------------------


class StartJobRequest(BaseModel):
    mission_id: str
    area: str = "all"
    period: str = "6m"
    detail: str = "summary"
    org_ids: List[str] = []
    is_admin: bool = False
    patient_id: Optional[str] = None


# -- POST /research/jobs ------------------------------------------------------


@app.post("/research/jobs", dependencies=[Depends(verify_service_token)])
def start_research_job(body: StartJobRequest) -> dict[str, Any]:
    """Queue a new research mission run.

    Returns immediately with job_id.
    Subscribe to GET /research/progress/{job_id} for live status.
    """
    store = get_store()
    job = store.create(
        mission_id=body.mission_id,
        area=body.area,
        period=body.period,
        detail=body.detail,
        org_ids=body.org_ids,
        is_admin=body.is_admin,
        patient_id=body.patient_id,
    )
    submit_job(job, store)
    logger.info("Research job created: %s mission=%s", job.job_id, body.mission_id)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stream_path": f"/research/progress/{job.job_id}",
    }


# -- GET /research/jobs -------------------------------------------------------


@app.get("/research/jobs", dependencies=[Depends(verify_service_token)])
def list_jobs() -> dict[str, Any]:
    """List recent research jobs."""
    store = get_store()
    return {"jobs": store.list_recent(limit=50)}


# -- GET /research/jobs/{job_id} ----------------------------------------------


@app.get("/research/jobs/{job_id}", dependencies=[Depends(verify_service_token)])
def get_job(job_id: str) -> dict[str, Any]:
    """Return full job detail including result."""
    store = get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job.to_dict()


# -- DELETE /research/jobs/{job_id} -------------------------------------------


@app.delete("/research/jobs/{job_id}", dependencies=[Depends(verify_service_token)])
def cancel_job(job_id: str) -> dict[str, Any]:
    """Mark a queued job as cancelled.

    Running jobs cannot be interrupted mid-algorithm.
    """
    store = get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    if job.status in {"done", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Job is already {job.status} -- cannot cancel",
        )
    store.update(job, status="cancelled", completed_at=time.time())
    return {"job_id": job_id, "status": "cancelled"}


# -- GET /research/progress/{job_id} -- SSE relay ----------------------------


@app.get("/research/progress/{job_id}", dependencies=[Depends(verify_service_token)])
def stream_progress(job_id: str):
    """Subscribe to research job progress via SSE.

    Relays Redis pub/sub messages from channel ``research:{job_id}``
    to the client.  Closes when the job reaches a terminal state or
    after _IDLE_TIMEOUT_S seconds of inactivity.
    """
    events: queue.Queue[Optional[dict]] = queue.Queue()

    def _redis_listener() -> None:
        try:
            import redis as _redis

            r = _redis.from_url(REDIS_URL)
            ps = r.pubsub(ignore_subscribe_messages=True)
            ps.subscribe(f"research:{job_id}")
            idle_s = 0.0
            while idle_s < _IDLE_TIMEOUT_S:
                msg = ps.get_message(timeout=1.0)
                if msg is None:
                    idle_s += 1.0
                    continue
                idle_s = 0.0
                if msg.get("type") != "message":
                    continue
                try:
                    data = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                events.put(data)
                if data.get("type") in {"done", "failed", "cancelled"}:
                    break
        except Exception as exc:
            events.put({"type": "error", "message": str(exc), "job_id": job_id})
        finally:
            events.put(None)

    threading.Thread(target=_redis_listener, daemon=True).start()

    def _generate():
        while True:
            try:
                event = events.get(timeout=2.0)
            except queue.Empty:
                yield _fmt_sse(
                    "heartbeat",
                    {"type": "heartbeat", "ts": time.time(), "job_id": job_id},
                )
                continue
            if event is None:
                break
            yield _fmt_sse(str(event.get("type", "message")), event)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -- GET /health --------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    store = get_store()
    jobs = store.list_recent(limit=100)
    running = sum(1 for j in jobs if j.get("status") == "running")
    return {
        "status": "ok",
        "service": "research-worker",
        "running_jobs": running,
        "total_recent_jobs": len(jobs),
    }


# -- Helpers ------------------------------------------------------------------


def _fmt_sse(event_type: str, payload: dict) -> str:
    data = json.dumps(payload, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"


# -- Entry point --------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "services.research_worker.app.main:app",
        host="0.0.0.0",
        port=8007,
        log_level="info",
    )
