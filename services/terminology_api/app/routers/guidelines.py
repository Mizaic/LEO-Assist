"""Guideline evaluation and bitmap lifecycle endpoints.

Provides:
  POST /terminology/guidelines/evaluate          -- patient SNOMED code evaluation
  POST /terminology/guidelines/bitmap/compile    -- compile active rules into bitmaps
  GET  /terminology/guidelines/bitmap/versions   -- list compiled versions
  PUT  /terminology/guidelines/bitmap/versions/{version}/activate -- set active version
  GET  /terminology/guidelines/bitmap/status     -- active version summary
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_compiler import GuidelineCompiler
from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator

logger = logging.getLogger(__name__)
router = APIRouter()

_compile_jobs: dict[str, dict] = {}


class EvaluateRequest(BaseModel):
    """Request body for patient guideline evaluation."""

    patient_codes: list[str]
    pathway_id: str | None = None


@router.post("/guidelines/evaluate")
def evaluate_patient(req: EvaluateRequest) -> dict:
    """Evaluate a patient's SNOMED codes against the active guideline ruleset.

    Returns the list of guideline rules that match the patient's clinical
    findings.  Results are deterministic and auditable -- the same inputs
    always produce the same outputs.

    Fast: typically completes in under 10ms for rulesets of up to 500 rules.
    """
    evaluator = GuidelineEvaluator()
    return evaluator.evaluate_patient(req.patient_codes, req.pathway_id)


@router.post("/guidelines/bitmap/compile", status_code=202)
async def compile_bitmap(background_tasks: BackgroundTasks) -> dict:
    """Compile all active AppropriatenessRules into a new bitmap version.

    This is an expensive operation that runs in the background.
    Only rules with status ``active`` are compiled -- rules awaiting review
    are never included.

    Returns a job ID immediately. Check
    ``GET /terminology/guidelines/bitmap/status`` to see when compilation
    completes.
    """
    job_id = str(uuid.uuid4())
    version = f"v{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    _compile_jobs[job_id] = {
        "job_id": job_id,
        "version": version,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    background_tasks.add_task(_run_compile, job_id, version)
    return {"job_id": job_id, "version": version}


@router.get("/guidelines/bitmap/versions")
def list_versions() -> list[dict]:
    """List all compiled ruleset versions in Redis.

    Each entry shows the version name and whether it is currently active.
    """
    store = BitmapStore()
    versions = store.list_versions()
    current = store.get_current_version_name()
    return [
        {"version": v, "active": v == current}
        for v in versions
    ]


@router.put("/guidelines/bitmap/versions/{version}/activate")
def activate_version(version: str) -> dict:
    """Set the active bitmap version used for patient evaluation.

    This change takes effect immediately for all subsequent evaluation calls.
    Use the Compile and Go Live panel in the admin UI, which shows a
    confirmation prompt before calling this endpoint.
    """
    store = BitmapStore()
    ruleset = store.get_ruleset(version)
    if not ruleset:
        raise HTTPException(
            status_code=404,
            detail=f"Ruleset version {version!r} not found. Compile it first.",
        )
    store.set_current_version(version)
    return {"version": version, "activated": True}


@router.get("/guidelines/bitmap/status")
def bitmap_status() -> dict:
    """Return a summary of the currently active bitmap ruleset.

    Includes the active version name, number of compiled rules, and
    compile timestamp. The admin UI uses this to show whether the bitmap
    is up to date.
    """
    store = BitmapStore()
    ruleset = store.get_current_ruleset()
    if not ruleset:
        return {
            "active_version": None,
            "rule_count": 0,
            "compile_timestamp": None,
            "message": "No active ruleset. Compile one from the admin panel.",
        }
    return {
        "active_version": ruleset.get("version"),
        "rule_count": len(ruleset.get("rules", [])),
        "compile_timestamp": ruleset.get("compile_timestamp"),
    }


async def _run_compile(job_id: str, version: str) -> None:
    """Background task: compile rules and update job status."""
    try:
        compiler = GuidelineCompiler()
        summary = await compiler.compile_and_store(version)
        _compile_jobs[job_id].update({
            "status": "done",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            **summary,
        })
    except Exception as exc:
        logger.exception("Bitmap compile failed for version %s", version)
        _compile_jobs[job_id].update({
            "status": "error",
            "error": str(exc),
        })
