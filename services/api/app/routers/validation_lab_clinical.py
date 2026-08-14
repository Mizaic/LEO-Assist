"""Validation Lab findings and clinical PipelineRun open.

Atlas:
  DI: DI-562F2C9E, DI-C953EF73, DI-238DA59A
  DO: DO-4FD76836
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from app.deps import require_admin_or_service
from libs.auth.org_scope import CallerScope
from libs.validation_lab import findings as finding_service
from libs.validation_lab.clinical_runs import (
    find_pipeline_runs,
    list_clinical_patients,
    list_recent_pipeline_runs,
)
from libs.validation_lab.findings import FindingError

router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])


class CreateFindingBody(BaseModel):
    stage_id: Literal["extract", "post", "terminology", "persist", "compliance", "sbar"]
    category: Literal[
        "extraction", "context", "guard", "phrase_mapping", "guideline_rule"
    ]
    target: str = Field(default="", max_length=512)
    note: str = Field(default="", max_length=1000)
    status: Literal["open", "routed", "retested", "closed"] = "open"


def _client() -> PatientGraphClient:
    return PatientGraphClient()


@router.post("/runs/{run_id}/findings", status_code=201)
def create_finding(
    run_id: str,
    body: CreateFindingBody,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    client = _client()
    try:
        return finding_service.create_finding(
            client,
            run_id=run_id,
            stage_id=body.stage_id,
            category=body.category,
            target=body.target,
            note=body.note,
            status=body.status,
        )
    except FindingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/runs/{run_id}/findings")
def list_run_findings(
    run_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> list[dict[str, Any]]:
    client = _client()
    try:
        return finding_service.list_findings_for_run(client, run_id)
    finally:
        client.close()


@router.get("/findings")
def list_open_findings(
    limit: int = Query(default=20, ge=1, le=100),
    _scope: CallerScope = Depends(require_admin_or_service),
) -> list[dict[str, Any]]:
    client = _client()
    try:
        return finding_service.list_open_findings(client, limit=limit)
    finally:
        client.close()


@router.get("/pipeline-runs")
def list_pipeline_runs(
    limit: int = Query(default=30, ge=1, le=100),
    q: str | None = Query(default=None),
    mode: Literal["patient", "letters"] = Query(default="patient"),
    _scope: CallerScope = Depends(require_admin_or_service),
) -> list[dict[str, Any]]:
    """Recent or looked-up PipelineRuns. Does not enqueue a new job."""
    client = _client()
    try:
        query = str(q or "").strip()
        if query:
            return find_pipeline_runs(
                client, query=query, limit=limit, mode=mode
            )
        return list_recent_pipeline_runs(client, limit=limit)
    finally:
        client.close()


@router.get("/clinical-patients")
def list_patients_with_runs(
    limit: int = Query(default=100, ge=1, le=200),
    q: str | None = Query(default=None),
    _scope: CallerScope = Depends(require_admin_or_service),
) -> list[dict[str, Any]]:
    """Patients with a pipeline run. Does not enqueue a new job."""
    client = _client()
    try:
        return list_clinical_patients(
            client,
            query=str(q or "").strip(),
            limit=limit,
        )
    finally:
        client.close()


@router.get("/pipeline-runs/{run_id}/inspector")
def get_pipeline_run_inspector(
    run_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    from libs.validation_lab import inspector as lab_inspector

    client = _client()
    try:
        return lab_inspector.get_pipeline_inspector(client, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/pipeline-runs/{run_id}/inspector/stages/{step_id}")
def get_pipeline_run_inspector_stage(
    run_id: str,
    step_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    from libs.validation_lab import inspector as lab_inspector

    client = _client()
    try:
        return lab_inspector.get_pipeline_stage_detail(
            client,
            pipeline_run_id=run_id,
            step_id=step_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()
