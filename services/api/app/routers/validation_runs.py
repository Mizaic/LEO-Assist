"""Generic validation-run API for UN-scoped workflows."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.services.validation_workflow_runner import (
    execute_validation_workflow_sync,
    validation_workflow_catalog,
)

router = APIRouter(prefix="/validation-runs", tags=["validation-runs"])

_RUNS: dict[str, dict[str, Any]] = {}


class ValidationRunRequest(BaseModel):
    case_id: str | None = None
    encounter_text: str | None = None
    initial_state: dict[str, Any] = Field(default_factory=dict)
    corpus_version: str | None = None


def _start_run(run_id: str, un_id: str, request: ValidationRunRequest) -> None:
    _RUNS[run_id]["status"] = "running"
    state = dict(request.initial_state)
    if request.case_id:
        state["case_id"] = request.case_id
    if request.encounter_text:
        state["encounter_text"] = request.encounter_text
    state["corpus_version"] = request.corpus_version
    try:
        result = execute_validation_workflow_sync(un_id=un_id, initial_state=state)
    except Exception as exc:
        _RUNS[run_id].update(
            {
                "status": "error",
                "error": str(exc),
                "finished_at": time.time(),
            }
        )
        return
    _RUNS[run_id].update(
        {
            "status": result.get("status", "completed"),
            "result": result,
            "finished_at": time.time(),
        }
    )


@router.get("/catalog")
def list_validation_workflows() -> dict[str, Any]:
    return {"workflows": validation_workflow_catalog()}


@router.post("/{un_id}")
def create_validation_run(
    un_id: str,
    request: ValidationRunRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    workflow = next(
        (item for item in validation_workflow_catalog() if item["un_id"] == un_id),
        None,
    )
    if not workflow:
        raise HTTPException(status_code=404, detail=f"No workflow for {un_id}")
    run_id = f"valrun-{uuid.uuid4().hex[:12]}"
    _RUNS[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "un_id": un_id,
        "val_id": workflow["val_id"],
        "plan_definition_id": workflow["plan_definition_id"],
        "corpus_version": request.corpus_version,
        "created_at": time.time(),
    }
    background_tasks.add_task(_start_run, run_id, un_id, request)
    return _RUNS[run_id]


@router.get("/{run_id}")
def get_validation_run(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run
