"""NER Training Worker service.

Always-on FastAPI service (port 8005) that manages training jobs:
fine-tunes Bio_ClinicalBERT-backed spaCy NER on approved TrainingLabel data.

Routes
------
POST /train/jobs                   — trigger a training run
GET  /train/jobs                   — list all jobs
GET  /train/jobs/{job_id}          — job detail + logs + metrics
DELETE /train/jobs/{job_id}        — cancel queued/running job
GET  /train/progress/{job_id}      — SSE relay from Redis pub/sub
GET  /health                       — service health
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.job_store import REDIS_URL, get_store
from app.job_runner import preload_training_modules, submit_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_IDLE_TIMEOUT_S = 300


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Warm heavy imports on startup so the first job has no cold-start."""
    if os.getenv("TRAINING_PRELOAD_IMPORTS", "true").lower() not in {"0", "false", "no"}:
        t0 = time.perf_counter()
        try:
            preload_training_modules()
            logger.info("Startup warmup finished in %.2fs", time.perf_counter() - t0)
        except Exception as exc:
            logger.warning("Startup warmup failed after %.2fs: %s", time.perf_counter() - t0, exc)
    yield


app = FastAPI(
    title="NER Training Worker",
    version="1.0.0",
    description=(
        "Manages Bio_ClinicalBERT NER fine-tuning jobs. "
        "Reads TrainingLabel nodes from Neo4j, trains the NER head, "
        "evaluates, and uploads the artifact to Azure Blob."
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


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class StartJobRequest(BaseModel):
    base_model_version: str = ""
    notes: str = ""
    triggered_by: str = "ui"


# ------------------------------------------------------------------
# POST /train/jobs
# ------------------------------------------------------------------


@app.post("/train/jobs")
def start_training_job(body: StartJobRequest) -> dict[str, Any]:
    """Queue a new training run.

    Returns immediately with job_id.  Subscribe to
    GET /train/progress/{job_id} for live updates.
    """
    store = get_store()
    job = store.create(
        base_model_version=body.base_model_version,
        hf_model_name=os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT"),
        notes=body.notes,
        triggered_by=body.triggered_by,
    )
    submit_job(job, store)
    logger.info("Training job created: %s triggered_by=%s", job.job_id, body.triggered_by)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stream_path": f"/train/progress/{job.job_id}",
    }


# ------------------------------------------------------------------
# GET /train/jobs
# ------------------------------------------------------------------


@app.get("/train/jobs")
def list_jobs() -> dict[str, Any]:
    """List all training jobs (most recent first)."""
    store = get_store()
    return {"jobs": store.list_all(log_tail=25)}


# ------------------------------------------------------------------
# GET /train/jobs/{job_id}
# ------------------------------------------------------------------


@app.get("/train/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Return full job detail including log lines and metrics."""
    store = get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job.to_dict(log_tail=500)


# ------------------------------------------------------------------
# DELETE /train/jobs/{job_id}
# ------------------------------------------------------------------


@app.delete("/train/jobs/{job_id}")
def cancel_job(job_id: str) -> dict[str, Any]:
    """Mark a queued job as cancelled.

    Running jobs cannot be cancelled mid-flight (spaCy subprocess runs to
    completion or times out).  Mark as cancelled so the result is ignored.
    """
    store = get_store()
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    if job.status in {"done", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Job is already {job.status} — cannot cancel",
        )
    store.update(job, status="cancelled")
    return {"job_id": job_id, "status": "cancelled"}


# ------------------------------------------------------------------
# GET /train/progress/{job_id} — SSE relay
# ------------------------------------------------------------------


@app.get("/train/progress/{job_id}")
def stream_training_progress(job_id: str):
    """Subscribe to training job progress events via SSE.

    Relays Redis pub/sub messages from channel ``training:{job_id}``
    to the browser.  Closes automatically when the job reaches a
    terminal state or after _IDLE_TIMEOUT_S seconds of silence.
    """
    events: queue.Queue[Optional[dict]] = queue.Queue()

    def _redis_listener() -> None:
        try:
            import redis as _redis
            r = _redis.from_url(REDIS_URL)
            ps = r.pubsub(ignore_subscribe_messages=True)
            ps.subscribe(f"training:{job_id}")
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
                if data.get("status") in {"done", "failed", "cancelled"}:
                    break
        except Exception as exc:
            events.put({"type": "training_error", "message": str(exc), "job_id": job_id})
        finally:
            events.put(None)

    threading.Thread(target=_redis_listener, daemon=True).start()

    def _event_generator():
        # Generator closes when listener puts None (terminal state or timeout).
        # The 2-second queue timeout emits heartbeats to keep the connection alive.
        while True:
            try:
                event = events.get(timeout=2.0)
            except queue.Empty:
                yield _fmt_sse("heartbeat", {"type": "heartbeat", "ts": time.time(), "job_id": job_id})
                continue
            if event is None:
                break
            yield _fmt_sse(str(event.get("type", "message")), event)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------
# GET /health
# ------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, Any]:
    store = get_store()
    jobs = store.list_all(log_tail=0)
    running = sum(1 for j in jobs if j["status"] == "running")
    return {
        "status": "ok",
        "hf_base_model": os.getenv("TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT"),
        "running_jobs": running,
        "total_jobs": len(jobs),
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _fmt_sse(event_type: str, payload: dict) -> str:
    data = json.dumps(payload, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"
