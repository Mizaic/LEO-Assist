"""HTTP surface for the persistent test-patient library.

Mounted under ``/guidance/test-patients`` (the proxy at /api/* exposes
this to the browser).  All endpoints require the ai.admin role.

Endpoints:
  POST   /guidance/test-patients/dry-run     -- preview without saving
  POST   /guidance/test-patients             -- save (after dry-run)
  GET    /guidance/test-patients             -- list with scope filter
  GET    /guidance/test-patients/{id}        -- detail
  DELETE /guidance/test-patients/{id}
  POST   /guidance/test-patients/generate    -- auto-generate happy/fail/boundary
  POST   /guidance/test-patients/replay      -- regression replay
  GET    /guidance/test-patients/replay-reports        -- list reports
  GET    /guidance/test-patients/replay-reports/{id}   -- one report
  GET    /guidance/test-patients/guidelines  -- scope picker helper
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from app.services import test_patient_generator, test_patient_service
from app.services.test_patient_service import PatientPayload
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guidance", tags=["test-patients"])


def _client() -> CodingGraphClient:
    return CodingGraphClient()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PatientBody(BaseModel):
    codes: list[str] = Field(default_factory=list)
    age: float | None = None
    sex: Literal["male", "female", "other"] | None = None
    pathway_id: str | None = None
    name: str = ""
    description: str = ""
    generation_source: str = "manual"

    def to_payload(self) -> PatientPayload:
        return PatientPayload(
            codes=self.codes,
            age=self.age,
            sex=self.sex,
            pathway_id=self.pathway_id,
            name=self.name,
            description=self.description,
            generation_source=self.generation_source,
        )


class DryRunRequest(BaseModel):
    patient: PatientBody
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None


class ExpectationBody(BaseModel):
    rule_id: str
    fires: bool
    matched_branch_node_ids: list[str] = Field(default_factory=list)


class SaveRequest(BaseModel):
    patient: PatientBody
    guideline_id: str
    expectations: list[ExpectationBody] = Field(default_factory=list)
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None
    skip_if_exists: bool = True


class GenerateRequest(BaseModel):
    scope_type: Literal["rule", "branch", "guideline", "all"] = "guideline"
    guideline_id: str | None = None
    rule_id: str | None = None
    branch_node_id: str | None = None
    depth: Literal["minimal_pair", "boundary_plus_pairs"] = "boundary_plus_pairs"
    exclude_existing: bool = True


class DiagnoseRequest(BaseModel):
    """Request body for per-rule diagnostic evaluation."""

    rule_id: str
    patient: PatientBody
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None


class ReplayRequest(BaseModel):
    patient_ids: list[str] | None = None
    guideline_id: str | None = None
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"
    ruleset_version: str | None = None
    persist_report: bool = True


class SandboxReplayRequest(BaseModel):
    """Compile UNSAVED draft rules and replay saved patients against them.

    Used by the rule editor's "Test against library" button. The compile
    is written to a custom-scoped key so it cannot collide with the
    production ruleset, and the sandbox is dropped automatically once
    the replay returns (with a Redis TTL fallback in case the cleanup
    request never lands).
    """

    rules: list[dict] = Field(default_factory=list)
    patient_ids: list[str] | None = None
    guideline_id: str | None = None
    sandbox_id: str | None = None
    policy_mode: Literal["advisory", "strict"] = "advisory"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/test-patients/dry-run")
def dry_run(
    body: DryRunRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Evaluate a patient against the live ruleset without saving."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.dry_run(
            client,
            body.patient.to_payload(),
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            ruleset_version=body.ruleset_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        client.close()


@router.post("/test-patients/diagnose")
def diagnose_rule(
    body: DiagnoseRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Return per-node match diagnostics for ONE rule against a patient.

    The diagnostic verdict is computed by the same bitmap evaluator that
    production uses to fire rules, so the per-leaf annotations are
    guaranteed to agree with the live firing decision.
    """
    _ = scope
    try:
        return test_patient_service.diagnose_rule_against_patient(
            body.patient.to_payload(),
            rule_id=body.rule_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            ruleset_version=body.ruleset_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/test-patients")
def save_patient(
    body: SaveRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Save a test patient + snapshot expectations.  Idempotent by hash."""
    client = _client()
    try:
        return test_patient_service.confirm_and_save(
            client,
            body.patient.to_payload(),
            [exp.model_dump() for exp in body.expectations],
            guideline_id=body.guideline_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            created_by=getattr(scope, "user_email", "") or "unknown",
            ruleset_version=body.ruleset_version,
            skip_if_exists=body.skip_if_exists,
        )
    finally:
        client.close()


@router.get("/test-patients")
def list_patients(
    guideline_id: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Return all saved patients matching the scope filter."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.list_patients(
            client,
            guideline_id=guideline_id,
            rule_id=rule_id,
            node_id=node_id,
            limit=limit,
        )
    finally:
        client.close()


@router.get("/test-patients/guidelines")
def list_guidelines(scope: CallerScope = Depends(require_admin)) -> list[dict]:
    """Return guidelines that have at least one active rule (for the picker)."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.list_guidelines_for_picker(client)
    finally:
        client.close()


@router.get("/test-patients/replay-reports")
def list_replay_reports(
    guideline_id: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    _ = scope
    client = _client()
    try:
        return test_patient_service.list_replay_reports(
            client,
            guideline_id=guideline_id,
            scope_type=scope_type,
            scope_id=scope_id,
            limit=limit,
        )
    finally:
        client.close()


@router.get("/test-patients/replay-reports/{report_id}")
def get_replay_report(
    report_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    _ = scope
    client = _client()
    try:
        report = test_patient_service.get_replay_report(client, report_id=report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Replay report not found")
        return report
    finally:
        client.close()


@router.get("/test-patients/{patient_id}")
def get_patient(
    patient_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    _ = scope
    client = _client()
    try:
        row = test_patient_service.get_patient(client, patient_id=patient_id)
        if not row:
            raise HTTPException(status_code=404, detail="Test patient not found")
        return row
    finally:
        client.close()


@router.delete("/test-patients/{patient_id}")
def delete_patient(
    patient_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    _ = scope
    client = _client()
    try:
        deleted = test_patient_service.delete_patient(
            client, patient_id=patient_id
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Test patient not found")
        return {"deleted": deleted, "patient_id": patient_id}
    finally:
        client.close()


@router.post("/test-patients/generate")
def generate_patients(
    body: GenerateRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Synthesise happy/fail/boundary patients across the requested scope.

    Returns proposed patients (not yet persisted) for the reviewer to
    dry-run and confirm.  ``exclude_existing`` skips any whose
    content_hash already exists in that guideline.
    """
    _ = scope
    client = _client()
    try:
        return test_patient_generator.generate(
            client,
            scope_type=body.scope_type,
            guideline_id=body.guideline_id,
            rule_id=body.rule_id,
            branch_node_id=body.branch_node_id,
            depth=body.depth,
            exclude_existing=body.exclude_existing,
        )
    finally:
        client.close()


@router.post("/test-patients/replay")
def replay(
    body: ReplayRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Replay saved patients and diff against their snapshots."""
    _ = scope
    client = _client()
    try:
        return test_patient_service.replay_scope(
            client,
            patient_ids=body.patient_ids,
            guideline_id=body.guideline_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            ruleset_version=body.ruleset_version,
            persist_report=body.persist_report,
        )
    finally:
        client.close()


@router.post("/test-patients/sandbox-replay")
def sandbox_replay(
    body: SandboxReplayRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Compile DRAFT rules into a sandbox bitmap and replay saved patients.

    Returns the same per-patient diff shape as
    ``/test-patients/replay`` so the existing ReplayResultsDialog can
    render the result, plus a ``compile`` summary so the UI can show
    how many of the draft rules actually compiled.

    Safe by construction: the compile writes to ``scope_type='custom'``
    only, and the sandbox is dropped before the response returns. A
    Redis TTL on the sandbox keys catches missed cleanups.
    """
    _ = scope
    if not body.rules:
        raise HTTPException(
            status_code=400, detail="sandbox-replay requires at least one rule"
        )
    client = _client()
    try:
        return test_patient_service.sandbox_replay(
            client,
            body.rules,
            patient_ids=body.patient_ids,
            guideline_id=body.guideline_id,
            sandbox_id=body.sandbox_id,
            policy_mode=body.policy_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        client.close()
