"""Guideline evaluation and bitmap lifecycle endpoints.

Atlas trace:
  DO: DO-E74B0605
  DI: DI-5E25E872
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E74B0605")

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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from libs.auth.service_auth import verify_service_token
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.services.bitmap_store import BitmapStore
from services.terminology_api.app.services.guideline_compiler import (
    CompileScope,
    GuidelineCompiler,
)
from services.terminology_api.app.services.guideline_evaluator import GuidelineEvaluator

logger = logging.getLogger(__name__)
router = APIRouter()

_compile_jobs: dict[str, dict] = {}


class ObservationInstance(BaseModel):
    """One numeric observation row on a patient.

    Phase 5e -- consumed by OBSERVATION leaves in the logic tree. The
    evaluator filters this list to the observable_id the leaf asks
    about, then applies the leaf's recency window and mode.

    Fields:
      observable_id  SNOMED concept id of the observable (must match
                     a leaf's ``observable_id``).
      value          Numeric reading. The evaluator canonicalises via
                     libs.units.observable_units before comparison.
      unit           Wire unit string. May be the canonical unit or
                     any registered alias.
      observed_at    ISO-8601 datetime. Naive timestamps are treated
                     as UTC by the evaluator.
    """

    observable_id: str
    value: float
    unit: str
    observed_at: str


class MedicationInstance(BaseModel):
    """One active medication row for the patient.

    Sprint 1 -- consumed by MEDICATION leaves in the logic tree.
    Fields mirror MedicationFact in libs.guidelines.patient_fact_bundle.

    Only medications with status="active" can match a MEDICATION leaf.
    All other statuses (stopped, planned, historical, unknown) fail closed.
    """

    drug_class: str
    status: str
    concept_id: str | None = None
    term: str = ""
    source_ids: list[str] = Field(default_factory=list)


class AllergyInstance(BaseModel):
    """One allergy row for the patient.

    Sprint 1 -- consumed by ALLERGY leaves in the logic tree.
    Fields mirror AllergyFact in libs.guidelines.patient_fact_bundle.

    Only allergies with status="active" can match an ALLERGY leaf.
    status="nkda" produces a distinct diagnostic reason (no known drug allergies).
    status="unknown" or absent list fails closed.
    """

    substance_concept_id: str
    status: str
    allergy_class: str | None = None
    term: str = ""
    source_ids: list[str] = Field(default_factory=list)


class TreatmentInstance(BaseModel):
    """One treatment history row for the patient.

    Sprint 1 -- consumed by TREATMENT_HISTORY leaves in the logic tree.
    Fields mirror TreatmentFact in libs.guidelines.patient_fact_bundle.

    Only treatments with outcome="failed" or outcome="not_tolerated" can match.
    All other outcomes fail closed.
    """

    treatment_class: str
    outcome: str
    concept_id: str | None = None
    duration_days: int | None = None
    term: str = ""
    source_ids: list[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    """Request body for patient guideline evaluation."""

    patient_codes: list[str]
    pathway_id: str | None = None
    patient_age: float | None = None
    """Patient age in decimal years.  Required for rules with age-based
    ``APPLIES_TO`` constraints (e.g. age >= 40).  Rules that require an age
    check are skipped when this is not supplied."""
    patient_sex: str | None = None
    """NHS PDS administrative gender.  Accepted values:
    ``"male"`` or ``"female"`` -- rules are evaluated and a limitation notice
    is returned reminding the clinician that PDS gender does not confirm
    reproductive anatomy.  ``"other"`` or ``"unknown"`` -- gender-specific
    and anatomy-specific NICE rules are not applied and ``gender_review_flag``
    is set in the response.  ``None`` (default) -- existing fail-closed
    behaviour; DEMOGRAPHIC sex nodes will not fire."""
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None
    observations: list[ObservationInstance] | None = None
    """Numeric observation history for the patient.  Required for
    rules that contain OBSERVATION leaves; absent / empty payloads
    fail those leaves CLOSED so the rule does not fire."""
    active_medications: list[MedicationInstance] | None = None
    """Active medications for the patient.  Required for rules that contain
    MEDICATION leaves; absent / empty payloads fail those leaves CLOSED."""
    allergies: list[AllergyInstance] | None = None
    """Allergy list for the patient.  Required for ALLERGY leaves;
    absent / empty payloads fail those leaves CLOSED."""
    treatment_history: list[TreatmentInstance] | None = None
    """Treatment history for the patient.  Required for TREATMENT_HISTORY leaves;
    absent / empty payloads fail those leaves CLOSED."""


class MissingFitReferral(BaseModel):
    referral_id: str
    organization_id: str
    matched_rules: list[dict] = Field(default_factory=list)


class MissingFitListRequest(BaseModel):
    organization_id: str
    referrals: list[MissingFitReferral] = Field(default_factory=list)


class CompileRequest(BaseModel):
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
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
    # DI candidate gate: compile writes a version; activate is separate.
    activate: bool = False


class ActivateRequest(BaseModel):
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"


@router.post("/guidelines/missing-fit-list")
def missing_fit_list(
    req: MissingFitListRequest,
    _: None = Depends(verify_service_token),
) -> dict:
    """List tenant referrals that should have had a FIT and did not."""
    from libs.guidelines.missing_fit_list import filter_missing_fit_referrals

    org = (req.organization_id or "").strip()
    if not org:
        raise HTTPException(status_code=422, detail="organization_id is required")
    kept = filter_missing_fit_referrals(
        [row.model_dump() for row in req.referrals],
        organization_id=org,
    )
    return {"organization_id": org, "referrals": kept}


@router.post("/guidelines/evaluate")
def evaluate_patient(req: EvaluateRequest) -> dict:
    """Evaluate a patient's SNOMED codes against the active guideline ruleset.

    Returns the list of guideline rules that match the patient's clinical
    findings.  Results are deterministic and auditable -- the same inputs
    always produce the same outputs.

    Fast: typically completes in under 10ms for rulesets of up to 500 rules.
    """
    client = KnowledgeGraphClient()
    with client.session() as session:
        evaluator = GuidelineEvaluator(neo4j_session=session)
        return evaluator.evaluate_patient(
            req.patient_codes,
            req.pathway_id,
            patient_age=req.patient_age,
            patient_sex=req.patient_sex,
            scope_type=req.scope_type,
            scope_id=req.scope_id,
            ruleset_version=req.ruleset_version,
            patient_observations=(
                [obs.model_dump() for obs in req.observations] if req.observations else None
            ),
            active_medications=(
                [m.model_dump() for m in req.active_medications]
                if req.active_medications
                else None
            ),
            allergies=([a.model_dump() for a in req.allergies] if req.allergies else None),
            treatment_history=(
                [t.model_dump() for t in req.treatment_history]
                if req.treatment_history
                else None
            ),
        )


class DiagnoseRequest(BaseModel):
    """Request body for per-rule diagnostic evaluation."""

    rule_id: str
    patient_codes: list[str]
    patient_age: float | None = None
    patient_sex: str | None = None
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None
    observations: list[ObservationInstance] | None = None
    """Same shape as EvaluateRequest.observations -- needed when the
    diagnosed rule contains OBSERVATION leaves so the per-leaf
    annotated tree can show fire / no-fire instead of failing closed
    silently."""
    active_medications: list[MedicationInstance] | None = None
    """Same shape as EvaluateRequest.active_medications."""
    allergies: list[AllergyInstance] | None = None
    """Same shape as EvaluateRequest.allergies."""
    treatment_history: list[TreatmentInstance] | None = None
    """Same shape as EvaluateRequest.treatment_history."""


@router.post("/guidelines/diagnose")
def diagnose_patient(req: DiagnoseRequest) -> dict:
    """Return per-node match diagnostics for ONE rule against a patient.

    Uses the same bitmap operations as ``/evaluate`` so the diagnostic
    verdict is guaranteed to agree with the production firing decision.
    The annotated tree is returned in the same shape as the compiled
    ``logic_tree`` so callers can render it hierarchically.

    Returns 404 with a structured ``detail`` dict when no ruleset is
    compiled or the rule_id is missing. The dict carries
    ``not_compiled``, ``rule_found``, ``recompile_hint``, and ``scope_*``
    so the UI can render a one-click "Compile now" banner instead of
    silently showing zero diagnostic information.
    """
    evaluator = GuidelineEvaluator()
    result = evaluator.diagnose(
        req.rule_id,
        req.patient_codes,
        patient_age=req.patient_age,
        patient_sex=req.patient_sex,
        scope_type=req.scope_type,
        scope_id=req.scope_id,
        ruleset_version=req.ruleset_version,
        patient_observations=(
            [obs.model_dump() for obs in req.observations] if req.observations else None
        ),
        active_medications=(
            [m.model_dump() for m in req.active_medications]
            if req.active_medications
            else None
        ),
        allergies=([a.model_dump() for a in req.allergies] if req.allergies else None),
        treatment_history=(
            [t.model_dump() for t in req.treatment_history]
            if req.treatment_history
            else None
        ),
    )
    if result is None or result.get("rule_found") is False:
        raise HTTPException(
            status_code=404,
            detail=result
            or {
                "not_compiled": True,
                "rule_found": False,
                "message": "No active ruleset compiled yet.",
                "scope_type": req.scope_type,
                "scope_id": req.scope_id,
            },
        )
    return result


class CompileDraftRequest(BaseModel):
    """Compile a hand-built list of v2 rules into a sandbox ruleset.

    The reviewer's "Test against library" flow uses this so they can
    replay saved test patients against an UNSAVED draft of a rule,
    without round-tripping through Neo4j. The draft is written to a
    custom-scoped key (e.g. ``ruleset:custom:draft-<uuid>``) and the
    caller is responsible for deleting it via
    ``DELETE /terminology/guidelines/scopes/{scope_type}/{scope_id}``
    once the replay completes.

    SAFETY: ``scope_type`` is forced to ``custom``; the endpoint refuses
    to write to global, guideline, domain, or subdomain scopes so a
    sandbox compile cannot collide with the production ruleset.
    """

    rules: list[dict] = Field(default_factory=list)
    scope_id: str
    policy_mode: Literal["advisory", "strict"] = "advisory"
    distance_child_override: int | None = None
    distance_parent_override: int | None = None
    ttl_seconds: int = 1800  # auto-expire abandoned sandboxes after 30 min


@router.post(
    "/guidelines/bitmap/compile-draft",
    status_code=200,
    dependencies=[Depends(verify_service_token)],
)
async def compile_draft_bitmap(body: CompileDraftRequest) -> dict:
    """Compile UNSAVED draft rules into a sandbox bitmap ruleset.

    Synchronous: rule-editor flows want the result inline. The compile
    is small (typically a single rule) so the latency cost is dominated
    by SNOMED closure expansion against Neo4j.

    Returns the version + scope so the caller can immediately POST to
    ``/guidelines/evaluate`` using the same scope_type=custom,
    scope_id=<sandbox>.
    """
    if not body.rules:
        raise HTTPException(
            status_code=400, detail="compile-draft requires at least one rule"
        )
    if not body.scope_id:
        raise HTTPException(status_code=400, detail="compile-draft requires a scope_id")
    scope = CompileScope.from_values("custom", body.scope_id)
    if scope.scope_type != "custom":
        raise HTTPException(
            status_code=400,
            detail="compile-draft only writes to scope_type='custom'",
        )
    version = f"draft-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    compiler = GuidelineCompiler()
    try:
        summary = await compiler.compile_drafts(
            version,
            body.rules,
            scope=scope,
            policy_mode=body.policy_mode,
            distance_child_override=body.distance_child_override,
            distance_parent_override=body.distance_parent_override,
            ttl_seconds=body.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return summary


@router.delete(
    "/guidelines/scopes/{scope_type}/{scope_id}",
    dependencies=[Depends(verify_service_token)],
)
def delete_scope(scope_type: str, scope_id: str) -> dict:
    """Drop every Redis key for a sandbox scope.

    Used by the rule-editor sandbox flow to clean up after a draft
    replay. Refuses to delete the global scope so an accidental call
    cannot wipe production rules.
    """
    if scope_type.strip().lower() == "global":
        raise HTTPException(
            status_code=400,
            detail="Refusing to delete the global production scope.",
        )
    store = BitmapStore()
    try:
        deleted = store.delete_scope(scope_type, scope_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "keys_deleted": deleted,
    }


@router.post(
    "/guidelines/bitmap/compile",
    status_code=202,
    dependencies=[Depends(verify_service_token)],
)
async def compile_bitmap(
    background_tasks: BackgroundTasks,
    body: CompileRequest | None = None,
) -> dict:
    """Compile all active AppropriatenessRules into a new bitmap version.

    This is an expensive operation that runs in the background.
    Only rules with status ``active`` are compiled -- rules awaiting review
    are never included.

    By default the new version is a **candidate** (``activate=false``) and
    does not become live. Pass ``activate=true`` only when an explicit
    go-live is intended. Prefer Activate after fixture + historic tests.

    Returns a job ID immediately. Poll
    ``GET /terminology/guidelines/bitmap/jobs/{job_id}`` or list versions.
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
        "activate": bool(body.activate),
    }
    background_tasks.add_task(_run_compile, job_id, version, body.model_dump())
    return {
        "job_id": job_id,
        "version": version,
        "scope_type": scope.scope_type,
        "scope_id": scope.scope_id,
        "activate": bool(body.activate),
        "status": "candidate" if not body.activate else "activating",
    }


@router.get("/guidelines/bitmap/jobs/{job_id}")
def get_compile_job(job_id: str) -> dict:
    """Return in-memory compile job status for candidate polling."""
    job = _compile_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Compile job not found")
    return dict(job)


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
        {
            "version": v,
            "active": v == current,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
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
        ruleset = (
            store.get_ruleset(version, scope_type=scope_type, scope_id=scope_id) or {}
        )
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


@router.put(
    "/guidelines/bitmap/versions/{version}/activate",
    dependencies=[Depends(verify_service_token)],
)
def activate_version(version: str, body: ActivateRequest | None = None) -> dict:
    """Set the active bitmap version used for patient evaluation.

    This change takes effect immediately for all subsequent evaluation calls.
    Use the Compile and Go Live panel in the admin UI, which shows a
    confirmation prompt before calling this endpoint.
    """
    body = body or ActivateRequest()
    store = BitmapStore()
    ruleset = store.get_ruleset(
        version, scope_type=body.scope_type, scope_id=body.scope_id
    )
    if not ruleset:
        raise HTTPException(
            status_code=404,
            detail=f"Ruleset version {version!r} not found. Compile it first.",
        )
    store.set_current_version(
        version, scope_type=body.scope_type, scope_id=body.scope_id
    )
    return {
        "version": version,
        "activated": True,
        "scope_type": body.scope_type,
        "scope_id": body.scope_id,
    }


@router.post(
    "/guidelines/bitmap/rollback",
    dependencies=[Depends(verify_service_token)],
)
def rollback_version(body: ActivateRequest | None = None) -> dict:
    body = body or ActivateRequest()
    store = BitmapStore()
    versions = store.list_versions(scope_type=body.scope_type, scope_id=body.scope_id)
    current = store.get_current_version_name(
        scope_type=body.scope_type, scope_id=body.scope_id
    )
    if len(versions) < 2:
        raise HTTPException(
            status_code=400, detail="No prior version available for rollback."
        )
    previous = [v for v in versions if v != current][-1]
    store.set_current_version(
        previous, scope_type=body.scope_type, scope_id=body.scope_id
    )
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

    Includes the active version name, number of compiled rules, their
    rule_ids, and compile timestamp. The admin UI uses this to show
    whether the bitmap is up to date and which rules are compiled.
    """
    store = BitmapStore()
    ruleset = store.get_current_ruleset(scope_type=scope_type, scope_id=scope_id)
    if not ruleset:
        return {
            "active_version": None,
            "rule_count": 0,
            "rule_ids": [],
            "compile_timestamp": None,
            "message": "No active ruleset. Compile one from the admin panel.",
            "scope_type": scope_type,
            "scope_id": scope_id,
        }
    rules = ruleset.get("rules") or []
    rule_ids = [
        rid
        for rule in rules
        if isinstance(rule, dict)
        for rid in [str(rule.get("rule_id") or rule.get("id") or "").strip()]
        if rid
    ]
    return {
        "active_version": ruleset.get("version"),
        "rule_count": len(rules),
        "rule_ids": rule_ids,
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
        scope = CompileScope.from_values(
            request_body.get("scope_type"), request_body.get("scope_id")
        )
        summary = await compiler.compile_and_store(
            version,
            scope=scope,
            policy_mode=request_body.get("policy_mode", "advisory"),
            include_rule_statuses=list(
                request_body.get("include_rule_statuses") or ["active"]
            ),
            policy_domain_id=request_body.get("policy_domain_id"),
            policy_subdomain_name=request_body.get("policy_subdomain_name"),
            policy_include_descendants=bool(
                request_body.get("policy_include_descendants", True)
            ),
            policy_depth=int(request_body.get("policy_depth") or 3),
            enforce_action_scope=bool(request_body.get("enforce_action_scope", False)),
            distance_child_override=request_body.get("distance_child_override"),
            distance_parent_override=request_body.get("distance_parent_override"),
            activate=bool(request_body.get("activate", False)),
        )
        _compile_jobs[job_id].update(
            {
                "status": "done",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                **summary,
            }
        )
        # Candidate testing against real Validation Lab patients is now a
        # manual step from the Bitmap Lifecycle UI (pinned via
        # guideline_ruleset_version on the real referral pipeline), not an
        # automatic post-compile hook. See libs/validation_lab/pipeline.py.
    except Exception as exc:
        logger.exception("Bitmap compile failed for version %s", version)
        _compile_jobs[job_id].update(
            {
                "status": "error",
                "error": str(exc),
            }
        )
