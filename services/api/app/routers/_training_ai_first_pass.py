"""AI first-pass endpoints (DI-LEO-AI-209 / DO-LEO-AI-206).

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Mounts onto the existing /training router via register_ai_first_pass_routes.
Keeps services/api/app/routers/training.py from growing further.

Endpoints:
  POST /training/candidates/ai-first-pass/jobs            -- queue
  GET  /training/candidates/ai-first-pass/jobs/{run_id}/events  -- SSE
  GET  /training/candidates/ai-first-pass/jobs/{run_id}   -- summary
  GET  /training/candidates/ai-first-pass/jobs            -- recent jobs
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.terminology.client import TerminologyClient

from app.services.candidate_ai_first_pass import AIFirstPassParams
from app.services.candidate_ai_first_pass._job_runner import (
    create_job,
    get_job,
    list_jobs,
    subscribe_events,
)

logger = logging.getLogger(__name__)


class AIFirstPassJobRequest(BaseModel):
    min_surface_match: float = Field(default=0.7, ge=0.0, le=1.0)
    semantic_vector_floor: float = Field(default=0.92, ge=0.0, le=1.0)
    semantic_min_surface: float = Field(default=0.66, ge=0.0, le=1.0)
    statuses: list[str] = Field(
        default_factory=lambda: ["pending", "processing", "failed"]
    )
    limit: int = Field(default=200, ge=1, le=2000)
    max_workers: int = Field(default=4, ge=1, le=8)
    few_shot_k: int = Field(default=5, ge=0, le=20)
    coder_max_retries: int = Field(default=2, ge=0, le=4)
    haiku_tier: str = Field(default="small")
    dry_run: bool = Field(default=False)


def _format_sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def register_ai_first_pass_routes(router) -> None:
    """Mount AI first-pass routes on the supplied router."""

    @router.post("/candidates/ai-first-pass/jobs")
    def queue_ai_first_pass_job(
        body: AIFirstPassJobRequest,
        scope: CallerScope = Depends(require_admin),
    ) -> dict[str, Any]:
        """Queue a new AI first-pass job; returns the run_id immediately."""
        # Local import keeps test substitution easy.
        from libs.neo4j_client.client import KnowledgeGraphClient

        params = AIFirstPassParams(
            min_surface_match=float(body.min_surface_match),
            semantic_vector_floor=float(body.semantic_vector_floor),
            semantic_min_surface=float(body.semantic_min_surface),
            statuses=tuple(body.statuses or []),
            limit=int(body.limit),
            max_workers=int(body.max_workers),
            few_shot_k=int(body.few_shot_k),
            coder_max_retries=int(body.coder_max_retries),
            haiku_tier=str(body.haiku_tier or "small"),
            dry_run=bool(body.dry_run),
        )

        state = create_job(
            client_factory=KnowledgeGraphClient,
            terminology_factory=TerminologyClient,
            params=params,
            run_in_background=True,
        )

        logger.info(
            "ai_first_pass.queue actor=%s run_id=%s limit=%d max_workers=%d "
            "dry_run=%s",
            getattr(scope, "email", "unknown"),
            state.run_id,
            params.limit,
            params.max_workers,
            params.dry_run,
        )
        return {
            "run_id": state.run_id,
            "status": state.status,
            "params": dict(state.params),
        }

    @router.get("/candidates/ai-first-pass/jobs/{run_id}/events")
    def stream_ai_first_pass_events(
        run_id: str,
        scope: CallerScope = Depends(require_admin),
    ):
        """Server-Sent Events stream for one AI first-pass job."""
        _ = scope

        if get_job(run_id) is None:
            raise HTTPException(status_code=404, detail="unknown run_id")

        def _generator():
            for event in subscribe_events(run_id, timeout_s=2.0, idle_timeout_s=600.0):
                yield _format_sse(str(event.get("type", "message")), event)

        return StreamingResponse(
            _generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/candidates/ai-first-pass/jobs/{run_id}")
    def get_ai_first_pass_job(
        run_id: str,
        scope: CallerScope = Depends(require_admin),
    ) -> dict[str, Any]:
        """Return the persisted summary of one AI first-pass job."""
        _ = scope
        state = get_job(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="unknown run_id")
        return state.to_dict()

    @router.get("/candidates/ai-first-pass/jobs")
    def list_ai_first_pass_jobs(
        scope: CallerScope = Depends(require_admin),
        limit: int = 20,
    ) -> dict[str, Any]:
        """List recent AI first-pass jobs (in-process only)."""
        _ = scope
        jobs = list_jobs(limit=limit)
        return {"jobs": [j.to_dict() for j in jobs]}
