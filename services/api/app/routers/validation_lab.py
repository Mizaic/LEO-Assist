"""Validation Lab HTTP API.

Atlas:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.db.neo4j_client import PatientGraphClient
from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.validation_lab.models import (
    EncounterSpec,
    PersistMode,
    PmhItem,
    ValidationCaseSpec,
)
from libs.validation_lab import service as lab_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])


class PmhItemBody(BaseModel):
    category: Literal["condition", "medication", "allergy"]
    concept_id: str = Field(..., min_length=1)
    term: str = ""


class EncounterBody(BaseModel):
    label: str = ""
    text: str = Field(..., min_length=1)
    date: str = ""


class CreateCaseBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    referral_text: str = Field(..., min_length=1)
    plan_id: str = ""
    case_id: str = ""
    patient_age: float | None = None
    patient_sex: str | None = None
    patient_name: str = ""
    pmh: list[PmhItemBody] = Field(default_factory=list)
    encounters: list[EncounterBody] = Field(default_factory=list)
    gold: dict[str, Any] = Field(default_factory=dict)


class StartRunBody(BaseModel):
    plan_id: str = Field(..., min_length=1)
    phase_ids: list[str] = Field(default_factory=list)
    persist_mode: Literal["production", "dry_run"] = "production"
    outputs: dict[str, Any] | None = None
    ruleset_version: str | None = None


class UpdateCaseBody(BaseModel):
    title: str | None = None
    referral_text: str | None = None
    plan_id: str | None = None
    gold: dict[str, Any] | None = None


def _client() -> PatientGraphClient:
    return PatientGraphClient()


@router.get("/governance")
def get_governance(_scope: CallerScope = Depends(require_admin)) -> dict[str, Any]:
    """Publish keep/retire matrix for UI and static VTs."""
    return {
        "lab_path": "/admin/validation-lab",
        "default_persist_mode": "production",
        "keep": [
            "pathway-builder-probes",
            "operations-run",
            "gold-dataset-sentences",
            "prompt-simulator",
            "coding-review",
            "local-guideline-import",
        ],
        "fold_into_lab": [
            "manual-sbar-playground",
            "scenario-runs",
            "extraction-scenarios-admin",
            "coding-validation-page",
            "quick-test",
            "test-patients-library",
            "test-patient-expectations",
        ],
        "retire_redirects": [
            "/admin/ai-summarisation",
            "/admin/extraction-scenarios",
            "/admin/coding-validation",
            "/admin/knowledge?tab=test-patients",
        ],
        "docs": "docs/VALIDATION-LAB.md",
        "atlas": {
            "un": "UN-4DCE95C8",
            "di": [
                "DI-724CD8A5",
                "DI-2289D095",
                "DI-9138BAC9",
                "DI-A898556B",
            ],
        },
    }


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(
    body: CreateCaseBody,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    case_id = (body.case_id or "").strip() or uuid.uuid4().hex
    spec = ValidationCaseSpec(
        case_id=case_id,
        title=body.title.strip(),
        referral_text=body.referral_text,
        plan_id=body.plan_id or "",
        created_by=getattr(scope, "email", None) or "validation-lab",
        patient_age=body.patient_age,
        patient_sex=body.patient_sex,
        patient_name=body.patient_name or "",
        pmh=[
            PmhItem(category=item.category, concept_id=item.concept_id, term=item.term)
            for item in body.pmh
        ],
        encounters=[
            EncounterSpec(label=enc.label, text=enc.text, date=enc.date)
            for enc in body.encounters
        ],
        gold=body.gold or {},
    )
    client = _client()
    try:
        return lab_service.create_case(client, spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("validation_lab.create_case failed")
        raise HTTPException(status_code=500, detail="Unable to create case") from exc
    finally:
        client.close()


@router.get("/cases")
def list_cases(
    limit: int = Query(50, ge=1, le=200),
    _scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    client = _client()
    try:
        return lab_service.list_cases(client, limit=limit)
    finally:
        client.close()


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.get_case(client, case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.patch("/cases/{case_id}")
def update_case(
    case_id: str,
    body: UpdateCaseBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.update_case(
            client,
            case_id,
            title=body.title,
            referral_text=body.referral_text,
            plan_id=body.plan_id,
            gold=body.gold,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/cases/{case_id}/graph-shape")
def get_graph_shape(
    case_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = _client()
    try:
        case = lab_service.get_case(client, case_id)
        return lab_service.probe_graph_shape(client, case)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.post("/cases/{case_id}/runs", status_code=status.HTTP_201_CREATED)
def start_run(
    case_id: str,
    body: StartRunBody,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    from libs.validation_lab.gold import RunOutputs
    from libs.validation_lab.pipeline import default_publish

    client = _client()
    try:
        outputs = RunOutputs.from_dict(body.outputs) if body.outputs else None
        persist = PersistMode(body.persist_mode)
        publish = default_publish if persist is PersistMode.production else None
        return lab_service.start_run(
            client,
            case_id=case_id,
            plan_id=body.plan_id,
            phase_ids=body.phase_ids,
            persist_mode=persist,
            outputs=outputs,
            publish=publish,
            ruleset_version=body.ruleset_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/cases/{case_id}/runs/{run_id}")
def get_run(
    case_id: str,
    run_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Poll a run's real status. Production runs are refreshed from the
    live pipeline (:PipelineRun / :AuditEvent) on every call until terminal."""
    client = _client()
    try:
        return lab_service.refresh_run(client, case_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.post("/cases/{case_id}/runs/{run_id}/promote-gold")
def promote_gold(
    case_id: str,
    run_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.promote_gold(client, case_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/cases/{case_id}/runs/{run_id}/score")
def score_run(
    case_id: str,
    run_id: str,
    _scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.score_case_run(client, case_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()
