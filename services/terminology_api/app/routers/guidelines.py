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
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_compiler import CompileScope, GuidelineCompiler
from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator

logger = logging.getLogger(__name__)
router = APIRouter()

_compile_jobs: dict[str, dict] = {}


class EvaluateRequest(BaseModel):
    """Request body for patient guideline evaluation."""

    patient_codes: list[str]
    pathway_id: str | None = None
    patient_age: float | None = None
    """Patient age in decimal years.  Required for rules with age-based
    ``APPLIES_TO`` constraints (e.g. age >= 40).  Rules that require an age
    check are skipped when this is not supplied."""
    patient_sex: str | None = None
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = "global"
    scope_id: str = "default"
    ruleset_version: str | None = None


class CompileRequest(BaseModel):
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = "global"
    scope_id: str = "default"
    policy_mode: Literal["advisory", "strict"] = "advisory"
    include_rule_statuses: list[str] = ["active"]
    policy_domain_id: str | None = None
    policy_subdomain_name: str | None = None
    policy_include_descendants: bool = True
    policy_depth: int = 3
    enforce_action_scope: bool = False
    distance_child_override: int | None = None
    distance_parent_override: int | None = None


class ActivateRequest(BaseModel):
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = "global"
    scope_id: str = "default"


@router.post("/guidelines/evaluate")
def evaluate_patient(req: EvaluateRequest) -> dict:
    """Evaluate a patient's SNOMED codes against the active guideline ruleset.

    Returns the list of guideline rules that match the patient's clinical
    findings.  Results are deterministic and auditable -- the same inputs
    always produce the same outputs.

    Fast: typically completes in under 10ms for rulesets of up to 500 rules.
    """
    evaluator = GuidelineEvaluator()
    return evaluator.evaluate_patient(
        req.patient_codes,
        req.pathway_id,
        patient_age=req.patient_age,
        patient_sex=req.patient_sex,
        scope_type=req.scope_type,
        scope_id=req.scope_id,
        ruleset_version=req.ruleset_version,
    )


@router.post("/guidelines/bitmap/compile", status_code=202)
async def compile_bitmap(
    background_tasks: BackgroundTasks,
    body: CompileRequest | None = None,
) -> dict:
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
    body = body or CompileRequest()
    scope = CompileScope.from_values(body.scope_type, body.scope_id)
    _compile_jobs[job_id] = {
        "job_id": job_id,
        "version": version,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scope_type": scope.scope_type,
        "scope_id": scope.scope_id,
        "policy_mode": body.policy_mode,
    }
    background_tasks.add_task(_run_compile, job_id, version, body.model_dump())
    return {
        "job_id": job_id,
        "version": version,
        "scope_type": scope.scope_type,
        "scope_id": scope.scope_id,
    }


@router.get("/guidelines/bitmap/versions")
def list_versions(
    scope_type: str = Query(default="global"),
    scope_id: str = Query(default="default"),
) -> list[dict]:
    """List all compiled ruleset versions in Redis.

    Each entry shows the version name and whether it is currently active.
    """
    store = BitmapStore()
    versions = store.list_versions(scope_type=scope_type, scope_id=scope_id)
    current = store.get_current_version_name(scope_type=scope_type, scope_id=scope_id)
    return [
        {"version": v, "active": v == current, "scope_type": scope_type, "scope_id": scope_id}
        for v in versions
    ]


@router.get("/guidelines/compiled")
def list_compiled(
    scope_type: str = Query(default="global"),
    scope_id: str = Query(default="default"),
) -> dict:
    store = BitmapStore()
    versions = store.list_versions(scope_type=scope_type, scope_id=scope_id)
    current = store.get_current_version_name(scope_type=scope_type, scope_id=scope_id)
    rows: list[dict] = []
    for version in versions:
        ruleset = store.get_ruleset(version, scope_type=scope_type, scope_id=scope_id) or {}
        rows.append(
            {
                "version": version,
                "active": version == current,
                "rule_count": len(ruleset.get("rules", [])),
                "compile_timestamp": ruleset.get("compile_timestamp"),
                "policy_mode": ruleset.get("policy_mode"),
                "compile_stats": ruleset.get("compile_stats") or {},
            }
        )
    return {"scope_type": scope_type, "scope_id": scope_id, "versions": rows}


@router.put("/guidelines/bitmap/versions/{version}/activate")
def activate_version(version: str, body: ActivateRequest | None = None) -> dict:
    """Set the active bitmap version used for patient evaluation.

    This change takes effect immediately for all subsequent evaluation calls.
    Use the Compile and Go Live panel in the admin UI, which shows a
    confirmation prompt before calling this endpoint.
    """
    body = body or ActivateRequest()
    store = BitmapStore()
    ruleset = store.get_ruleset(version, scope_type=body.scope_type, scope_id=body.scope_id)
    if not ruleset:
        raise HTTPException(
            status_code=404,
            detail=f"Ruleset version {version!r} not found. Compile it first.",
        )
    store.set_current_version(version, scope_type=body.scope_type, scope_id=body.scope_id)
    return {
        "version": version,
        "activated": True,
        "scope_type": body.scope_type,
        "scope_id": body.scope_id,
    }


@router.post("/guidelines/bitmap/rollback")
def rollback_version(body: ActivateRequest | None = None) -> dict:
    body = body or ActivateRequest()
    store = BitmapStore()
    versions = store.list_versions(scope_type=body.scope_type, scope_id=body.scope_id)
    current = store.get_current_version_name(scope_type=body.scope_type, scope_id=body.scope_id)
    if len(versions) < 2:
        raise HTTPException(status_code=400, detail="No prior version available for rollback.")
    previous = [v for v in versions if v != current][-1]
    store.set_current_version(previous, scope_type=body.scope_type, scope_id=body.scope_id)
    return {
        "rolled_back_to": previous,
        "scope_type": body.scope_type,
        "scope_id": body.scope_id,
    }


@router.get("/guidelines/bitmap/status")
def bitmap_status(
    scope_type: str = Query(default="global"),
    scope_id: str = Query(default="default"),
) -> dict:
    """Return a summary of the currently active bitmap ruleset.

    Includes the active version name, number of compiled rules, and
    compile timestamp. The admin UI uses this to show whether the bitmap
    is up to date.
    """
    store = BitmapStore()
    ruleset = store.get_current_ruleset(scope_type=scope_type, scope_id=scope_id)
    if not ruleset:
        return {
            "active_version": None,
            "rule_count": 0,
            "compile_timestamp": None,
            "message": "No active ruleset. Compile one from the admin panel.",
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
    return {
        "active_version": ruleset.get("version"),
        "rule_count": len(ruleset.get("rules", [])),
        "compile_timestamp": ruleset.get("compile_timestamp"),
        "scope_type": ruleset.get("scope_type") or scope_type,
        "scope_id": ruleset.get("scope_id") or scope_id,
        "policy_mode": ruleset.get("policy_mode"),
        "compile_stats": ruleset.get("compile_stats") or {},
    }


async def _run_compile(job_id: str, version: str, request_body: dict) -> None:
    """Background task: compile rules and update job status."""
    try:
        compiler = GuidelineCompiler()
        scope = CompileScope.from_values(request_body.get("scope_type"), request_body.get("scope_id"))
        summary = await compiler.compile_and_store(
            version,
            scope=scope,
            policy_mode=request_body.get("policy_mode", "advisory"),
            include_rule_statuses=list(request_body.get("include_rule_statuses") or ["active"]),
            policy_domain_id=request_body.get("policy_domain_id"),
            policy_subdomain_name=request_body.get("policy_subdomain_name"),
            policy_include_descendants=bool(request_body.get("policy_include_descendants", True)),
            policy_depth=int(request_body.get("policy_depth") or 3),
            enforce_action_scope=bool(request_body.get("enforce_action_scope", False)),
            distance_child_override=request_body.get("distance_child_override"),
            distance_parent_override=request_body.get("distance_parent_override"),
        )
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
