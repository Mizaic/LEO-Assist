"""Validation Lab HTTP API.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

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
from app.deps import require_admin_or_service
from libs.auth.org_scope import CallerScope
from libs.validation_lab.models import (
    AgConversationTurn,
    EncounterSpec,
    ObservationTrigger,
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


class AgTurnBody(BaseModel):
    category: Literal["REQUESTER", "RESPONDER"] = "REQUESTER"
    note: str = Field(..., min_length=1)
    sent_datetime: str = ""
    attachment_text: str = ""


class ObservationBody(BaseModel):
    observable_id: str = Field(..., min_length=1)
    value: float
    unit: str = Field(..., min_length=1)
    term: str = ""


class CreateCaseBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    summary: str = Field(default="", max_length=240)
    tags: list[str] = Field(default_factory=list)
    referral_text: str = ""
    case_type: Literal["referral", "ag"] = "referral"
    scenario_type: Literal["generic", "spo_ag", "ras_referral"] = "generic"
    plan_id: str = ""
    case_id: str = ""
    patient_age: float | None = None
    patient_sex: str | None = None
    patient_name: str = ""
    nhs_number: str = ""
    gp_practice_name: str = ""
    gp_encounter: EncounterBody | None = None
    reason_for_submission: str = ""
    verbalisation_seed: str = ""
    pmh: list[PmhItemBody] = Field(default_factory=list)
    encounters: list[EncounterBody] = Field(default_factory=list)
    gold: dict[str, Any] = Field(default_factory=dict)
    ag_thread: list[AgTurnBody] = Field(default_factory=list)
    ag_response_text: str = ""
    ag_request_attachments: list[str] = Field(default_factory=list)
    ag_ubrn: str = ""
    ethnicity_concept_id: str | None = None
    ethnicity_term: str | None = None
    performance_status_grade: int | None = None
    comorbidity_band: str | None = None
    core20_decile: int | None = None
    plus_group: str | None = None
    observations: list[ObservationBody] = Field(default_factory=list)


class PreviewPmhBody(BaseModel):
    pmh: list[PmhItemBody] = Field(default_factory=list)
    seed: str = "preview"


class StartRunBody(BaseModel):
    plan_id: str = Field(..., min_length=1)
    phase_ids: list[str] = Field(default_factory=list)
    persist_mode: Literal["production", "dry_run"] = "production"
    outputs: dict[str, Any] | None = None
    ruleset_version: str | None = None


class StartAgRunBody(BaseModel):
    ubrn: str = Field(..., min_length=1)
    plan_id: str = Field(..., min_length=1)
    phase_ids: list[str] = Field(default_factory=list)
    persist_mode: Literal["production", "dry_run"] = "production"
    ruleset_version: str | None = None
    guideline_id: str | None = None
    completeness_domain: str | None = None
    completeness_subdomain: str | None = None


class UpdateCaseBody(BaseModel):
    title: str | None = None
    referral_text: str | None = None
    plan_id: str | None = None
    gold: dict[str, Any] | None = None


def _client() -> PatientGraphClient:
    return PatientGraphClient()


@router.get("/governance")
def get_governance(
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
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
                "DI-D6E5F94E",
            ],
        },
    }


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(
    body: CreateCaseBody,
    scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    case_id = (body.case_id or "").strip() or uuid.uuid4().hex
    gp_enc = None
    if body.gp_encounter is not None:
        gp_enc = EncounterSpec(
            label=body.gp_encounter.label,
            text=body.gp_encounter.text,
            date=body.gp_encounter.date,
        )
    spec = ValidationCaseSpec(
        case_id=case_id,
        title=body.title.strip(),
        summary=(body.summary or "").strip(),
        tags=[t.strip() for t in (body.tags or []) if str(t).strip()][:8],
        referral_text=body.referral_text,
        case_type=body.case_type,
        scenario_type=body.scenario_type,
        plan_id=body.plan_id or "",
        created_by=getattr(scope, "email", None) or "validation-lab",
        patient_age=body.patient_age,
        patient_sex=body.patient_sex,
        patient_name=body.patient_name or "",
        nhs_number=body.nhs_number or "",
        gp_practice_name=body.gp_practice_name or "",
        gp_encounter=gp_enc,
        reason_for_submission=body.reason_for_submission or "",
        verbalisation_seed=body.verbalisation_seed or case_id,
        pmh=[
            PmhItem(category=item.category, concept_id=item.concept_id, term=item.term)
            for item in body.pmh
        ],
        encounters=[
            EncounterSpec(label=enc.label, text=enc.text, date=enc.date)
            for enc in body.encounters
        ],
        gold=body.gold or {},
        ag_thread=[
            AgConversationTurn(
                category=turn.category,
                note=turn.note,
                sent_datetime=turn.sent_datetime,
                attachment_text=turn.attachment_text,
            )
            for turn in body.ag_thread
        ],
        ag_response_text=body.ag_response_text or "",
        ag_request_attachments=list(body.ag_request_attachments or []),
        ag_ubrn=body.ag_ubrn or "",
        ethnicity_concept_id=body.ethnicity_concept_id,
        ethnicity_term=body.ethnicity_term,
        performance_status_grade=body.performance_status_grade,
        comorbidity_band=body.comorbidity_band,
        core20_decile=body.core20_decile,
        plus_group=body.plus_group,
        observations=[
            ObservationTrigger(
                observable_id=obs.observable_id,
                value=obs.value,
                unit=obs.unit,
                term=obs.term,
            )
            for obs in body.observations
        ],
    )
    if spec.scenario_type == "spo_ag":
        spec.case_type = "ag"
    if spec.scenario_type == "ras_referral":
        spec.case_type = "referral"
    if (
        spec.case_type == "referral"
        and spec.scenario_type != "ras_referral"
        and not spec.referral_text.strip()
    ):
        raise HTTPException(status_code=400, detail="referral_text is required")
    if spec.scenario_type == "ras_referral" and not (
        spec.reason_for_submission.strip() or spec.referral_text.strip()
    ):
        raise HTTPException(
            status_code=400, detail="reason_for_submission is required for ras_referral"
        )
    if spec.scenario_type in ("spo_ag", "ras_referral"):
        if spec.gp_encounter is None or not str(spec.gp_encounter.text or "").strip():
            raise HTTPException(
                status_code=400,
                detail="gp_encounter.text is required for SPoA scenarios",
            )
    if spec.scenario_type == "spo_ag" and not (
        spec.reason_for_submission.strip()
        or any(str(t.note or "").strip() for t in spec.ag_thread)
    ):
        raise HTTPException(
            status_code=400,
            detail="reason_for_submission or first REQUESTER note is required for spo_ag",
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


@router.post("/preview-pmh-narrative")
def preview_pmh_narrative(
    body: PreviewPmhBody,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    try:
        return lab_service.preview_pmh_narrative(
            None,
            pmh=[item.model_dump() for item in body.pmh],
            seed=body.seed or "preview",
        )
    except Exception as exc:
        logger.exception("validation_lab.preview_pmh_narrative failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cases")
def list_cases(
    limit: int = Query(200, ge=1, le=500),
    _scope: CallerScope = Depends(require_admin_or_service),
) -> list[dict[str, Any]]:
    client = _client()
    try:
        return lab_service.list_cases(client, limit=limit)
    finally:
        client.close()


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
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
    _scope: CallerScope = Depends(require_admin_or_service),
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


@router.delete("/cases/{case_id}")
def delete_case(
    case_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.delete_case(client, case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("validation_lab.delete_case failed")
        raise HTTPException(status_code=500, detail="Unable to delete case") from exc
    finally:
        client.close()


@router.get("/cases/{case_id}/graph-shape")
def get_graph_shape(
    case_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    client = _client()
    try:
        case = lab_service.get_case(client, case_id)
        return lab_service.probe_graph_shape(client, case)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.post("/ag-runs", status_code=status.HTTP_201_CREATED)
def start_ag_run(
    body: StartAgRunBody,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    from libs.validation_lab.ag_pipeline import AgPipelineError
    from libs.validation_lab.pipeline import default_publish

    client = _client()
    try:
        persist = PersistMode(body.persist_mode)
        publish = default_publish if persist is PersistMode.production else None
        return lab_service.start_ag_run(
            client,
            ubrn=body.ubrn.strip(),
            plan_id=body.plan_id,
            phase_ids=body.phase_ids,
            persist_mode=persist,
            publish=publish,
            ruleset_version=body.ruleset_version,
            guideline_id=body.guideline_id,
            completeness_domain=body.completeness_domain,
            completeness_subdomain=body.completeness_subdomain,
        )
    except AgPipelineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.get("/ag-runs/{run_id}")
def get_ag_run(
    run_id: str,
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.refresh_ag_run(client, run_id)
    finally:
        client.close()


@router.post("/cases/{case_id}/runs", status_code=status.HTTP_201_CREATED)
def start_run(
    case_id: str,
    body: StartRunBody,
    _scope: CallerScope = Depends(require_admin_or_service),
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
    _scope: CallerScope = Depends(require_admin_or_service),
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
    _scope: CallerScope = Depends(require_admin_or_service),
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
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    client = _client()
    try:
        return lab_service.score_case_run(client, case_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()
