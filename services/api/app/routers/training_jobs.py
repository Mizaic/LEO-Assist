"""Training job management router -- proxied to the training worker service.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: GET/POST /jobs, GET/DELETE /jobs/{job_id}.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.auth.service_auth import get_service_auth_header
from app.deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


TRAINING_WORKER_BASE = os.getenv("TRAINING_WORKER_URL", "http://localhost:8005").rstrip(
    "/"
)


async def _proxy_training_worker(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Forward a request to the training worker service."""
    url = f"{TRAINING_WORKER_BASE}{path}"
    headers = {**get_service_auth_header()}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(method, url, json=json_body, headers=headers)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Training worker unavailable at {TRAINING_WORKER_BASE}",
        ) from exc

    if resp.status_code >= 400:
        detail: Any
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except ValueError:
            detail = resp.text or f"Training worker error ({resp.status_code})"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail="Training worker returned invalid JSON"
        ) from exc


class _StartJobBody(BaseModel):
    base_model_version: str = ""
    notes: str = ""
    triggered_by: str = "api"


@router.get("/jobs")
async def list_training_jobs(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """List all NER training jobs (most recent first).

    Proxied to the training worker at GET /train/jobs.
    """
    return await _proxy_training_worker("GET", "/train/jobs")


@router.post("/jobs")
async def start_training_job(
    body: _StartJobBody,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Queue a new NER training run.

    Proxied to the training worker at POST /train/jobs.
    Returns immediately with job_id; subscribe to the SSE progress stream
    at GET /train/progress/{job_id} on the training worker directly.
    """
    return await _proxy_training_worker(
        "POST", "/train/jobs", json_body=body.model_dump()
    )


@router.get("/jobs/{job_id}")
async def get_training_job(
    job_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return full detail for a single training job.

    Proxied to the training worker at GET /train/jobs/{job_id}.
    """
    return await _proxy_training_worker("GET", f"/train/jobs/{job_id}")


@router.delete("/jobs/{job_id}")
async def cancel_training_job(
    job_id: str,
    scope: CallerScope = Depends(get_caller_scope),
    _admin: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Cancel a queued training job.

    Proxied to the training worker at DELETE /train/jobs/{job_id}.
    """
    return await _proxy_training_worker("DELETE", f"/train/jobs/{job_id}")
