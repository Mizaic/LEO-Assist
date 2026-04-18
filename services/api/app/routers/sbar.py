"""SBAR generation HTTP endpoints.

Routes
------
POST /sbar/jobs                         -- enqueue an SBAR generation job
GET  /sbar/jobs/{run_id}/events         -- SSE relay of orchestrator progress
GET  /sbar/assessments/{assessment_id}  -- read back a persisted Assessment

The producer is the Admin AI Summarisation Playground but any service
that needs an SBAR (a referral writer, a future encounter hook) can hit
the same enqueue endpoint or publish directly to the pipeline-jobs
queue with the same payload.

See DI-LEO-AI-186, DI-LEO-AI-190.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.deps import require_admin
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.sbar_assessment_queries import (
    GET_ASSESSMENT,
    assessment_to_dict,
)
from libs.sbar.events import SBARRequestPayload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sbar", tags=["sbar"])

PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_PROGRESS_IDLE_TIMEOUT_S = 300
_TERMINAL_EVENT_TYPES = frozenset(
    {"sbar_completed", "sbar_failed", "pipeline_error"}
)


class SBARJobResponse(BaseModel):
    run_id: str
    assessment_id: str
    status: str = "queued"


@router.post("/jobs", response_model=SBARJobResponse)
async def enqueue_sbar_job(
    body: dict[str, Any],
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> SBARJobResponse:
    """Validate, normalise, and publish an sbar_requested job."""
    run_id = str(body.get("run_id") or uuid.uuid4())
    body.setdefault("run_id", run_id)
    body.setdefault("event_type", "sbar_requested")
    body.setdefault("assessment_id", uuid.uuid4().hex)
    if scope and getattr(scope, "user_id", None) and not body.get("requested_by"):
        body["requested_by"] = scope.user_id
    if scope and getattr(scope, "tenant_id", None) and not body.get("tenant_id"):
        body["tenant_id"] = scope.tenant_id

    try:
        payload = SBARRequestPayload.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    bus = create_message_bus()
    try:
        await bus.send(
            PIPELINE_QUEUE,
            Message(
                body=json.dumps(payload.model_dump(mode="json")).encode("utf-8"),
                correlation_id=payload.run_id,
                subject="sbar-requested",
            ),
        )
    finally:
        await bus.close()

    return SBARJobResponse(
        run_id=payload.run_id,
        assessment_id=str(payload.assessment_id),
        status="queued",
    )


@router.get("/jobs/{run_id}/events")
def stream_sbar_events(
    run_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
):
    """Relay orchestrator progress events for *run_id* via Server-Sent Events.

    Connection auto-closes on a terminal event or after
    ``_PROGRESS_IDLE_TIMEOUT_S`` seconds of silence.
    """
    _ = scope
    events: queue.Queue[dict | None] = queue.Queue()

    def _redis_listener() -> None:
        try:
            import redis as _redis

            r = _redis.from_url(REDIS_URL)
            last_key = f"pipeline:last:{run_id}"
            last_raw = r.get(last_key)
            if last_raw:
                try:
                    if isinstance(last_raw, bytes):
                        last_raw = last_raw.decode("utf-8")
                    last_event = json.loads(last_raw)
                    if isinstance(last_event, dict):
                        events.put(last_event)
                        if last_event.get("type") in _TERMINAL_EVENT_TYPES:
                            return
                except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                    pass
            ps = r.pubsub(ignore_subscribe_messages=True)
            channel = f"pipeline:{run_id}"
            ps.subscribe(channel)
            idle_s = 0.0
            while idle_s < _PROGRESS_IDLE_TIMEOUT_S:
                msg = ps.get_message(timeout=1.0)
                if msg is None:
                    idle_s += 1.0
                    continue
                idle_s = 0.0
                if msg.get("type") != "message":
                    continue
                try:
                    data: dict = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                events.put(data)
                if data.get("type") in _TERMINAL_EVENT_TYPES:
                    break
        except Exception as exc:
            events.put({"type": "pipeline_error", "message": str(exc), "run_id": run_id})
        finally:
            events.put(None)

    threading.Thread(target=_redis_listener, daemon=True).start()

    def _format_sse(event_type: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def _event_generator():
        idle_ticks = 0
        while True:
            try:
                event = events.get(timeout=2.0)
            except queue.Empty:
                idle_ticks += 1
                yield _format_sse(
                    "heartbeat",
                    {"type": "heartbeat", "ts": time.time(), "run_id": run_id},
                )
                if idle_ticks > (_PROGRESS_IDLE_TIMEOUT_S // 2):
                    break
                continue
            if event is None:
                break
            idle_ticks = 0
            yield _format_sse(str(event.get("type", "message")), event)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    _ = scope
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                GET_ASSESSMENT, assessment_id=assessment_id
            ).single()
    finally:
        client.close()

    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Assessment {assessment_id!r} not found"
        )
    return assessment_to_dict(row)
