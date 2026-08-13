"""Patient EPR sub-resource endpoints.

Encounters, encounter detail, documents, SBAR assessments, safety alerts,
and episode milestones. Split from patients_epr.py to stay within 500 LOC.

Atlas trace:
  DO: DO-5D3EA371
  DI: DI-357A7468
"""

from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from libs.patient_documents.blob_url_signer import sign_patient_document_url
from libs.patient_documents.folder_label import resolve_document_folder_label

from .patients_epr_queries import (
    GET_ALERTS_ADMIN,
    GET_ALERTS_SCOPED,
    GET_ASSESSMENTS_ADMIN,
    GET_ASSESSMENTS_SCOPED,
    GET_CODED_ENTITIES_ADMIN,
    GET_CODED_ENTITIES_SCOPED,
    GET_DOCUMENTS_ADMIN,
    GET_DOCUMENTS_SCOPED,
    GET_ENCOUNTER_DETAIL_ADMIN,
    GET_ENCOUNTER_DETAIL_SCOPED,
    GET_ENCOUNTERS_ADMIN,
    GET_ENCOUNTERS_SCOPED,
    GET_MILESTONES,
    PATCH_ALERT,
)

router = APIRouter()


def _coerce_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SNOMED_SUFFIX = re.compile(r"\s*\([^)]+\)\s*$")


def _strip_snomed_suffix(name: str | None) -> str | None:
    if not name:
        return name
    return _SNOMED_SUFFIX.sub("", name).strip() or name


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class EncounterRow(BaseModel):
    encounter_id: str
    encounter_date: Optional[str] = None
    encounter_type: str = "Encounter"
    specialty: Optional[str] = None
    text_preview: Optional[str] = None
    coded_count: int = 0
    episode_id: Optional[str] = None


class CodedTerm(BaseModel):
    code_id: Optional[str] = None
    display: Optional[str] = None
    system: str = "SNOMED"
    evidence: Optional[str] = None
    evidence_sentence: Optional[str] = None
    assertion: Optional[str] = None
    confidence: Optional[float] = None
    value: Optional[str] = None
    unit: Optional[str] = None


class EncounterDetail(BaseModel):
    encounter_id: str
    encounter_date: Optional[str] = None
    encounter_type: str = "Encounter"
    specialty: Optional[str] = None
    full_text: str = ""
    episode_id: Optional[str] = None
    coded_terms: list[CodedTerm] = []


class SbarContent(BaseModel):
    sbar_id: str
    status: Optional[str] = None
    situation: Optional[str] = None
    background: Optional[str] = None
    assessment: Optional[str] = None
    recommendation: Optional[str] = None


class DocumentRow(BaseModel):
    document_id: str
    document_date: Optional[str] = None
    document_type: str = "Document"
    title: str = "Untitled"
    category: Optional[str] = None
    text_preview: Optional[str] = None
    full_text: str = ""
    content_type: Optional[str] = None
    original_url: Optional[str] = None
    markdown_url: Optional[str] = None
    episode_id: Optional[str] = None
    episode_label: str = "General"
    folder_label: str = "General"
    referral_id: Optional[str] = None
    chunk_count: int = 0
    sbar: Optional[SbarContent] = None


class AssessmentRow(BaseModel):
    assessment_id: str
    episode_id: Optional[str] = None
    episode_label: str = "Patient summary"
    scope: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    situation: Optional[str] = None
    background: Optional[str] = None
    assessment: Optional[str] = None
    recommendation: Optional[str] = None
    content: Optional[str] = None
    stt: Optional[str] = None
    stt_evidence: Optional[str] = None
    completeness_failed_count: Optional[int] = None
    background_parts: Optional[str] = None
    completeness_result_json: Optional[str] = None


class AlertRow(BaseModel):
    alert_id: str
    alert_type: str = "Alert"
    severity: str = "medium"
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    message: Optional[str] = None
    condition_context: Optional[str] = None
    guideline_ref: Optional[str] = None


class CodedEntityRow(BaseModel):
    entity_type: str
    name: str
    concept_id: Optional[str] = None


class MilestoneStep(BaseModel):
    milestone_type: str
    dates: list[str]


class EpisodeMilestones(BaseModel):
    episode_id: str
    referral_date: Optional[str] = None
    end_date: Optional[str] = None
    steps: list[MilestoneStep] = []


def _cypher_params(scope: CallerScope, patient_id: str, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"patient_id": patient_id, **extra}
    if not scope.is_admin:
        params["scope_org_ids"] = scope.org_ids
    return params


def _pick_query(scope: CallerScope, admin_q: str, scoped_q: str) -> str:
    return admin_q if scope.is_admin else scoped_q


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/patients/{patient_id}/encounters", response_model=list[EncounterRow])
def get_patient_encounters(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[EncounterRow]:
    """Encounter list with text preview for the encounter list panel."""
    query = _pick_query(scope, GET_ENCOUNTERS_ADMIN, GET_ENCOUNTERS_SCOPED)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **_cypher_params(scope, patient_id))
    finally:
        client.close()
    return [
        EncounterRow(
            encounter_id=r["encounter_id"],
            encounter_date=r.get("encounter_date"),
            encounter_type=r.get("encounter_type") or "Encounter",
            specialty=r.get("specialty"),
            text_preview=r.get("text_preview"),
            coded_count=int(r.get("coded_count") or 0),
            episode_id=r.get("episode_id"),
        )
        for r in rows
        if r.get("encounter_id")
    ]


@router.get(
    "/patients/{patient_id}/encounters/{encounter_id}",
    response_model=EncounterDetail,
)
def get_encounter_detail(
    patient_id: str,
    encounter_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> EncounterDetail:
    """Full encounter text with coded terms for the encounter viewer."""
    query = _pick_query(scope, GET_ENCOUNTER_DETAIL_ADMIN, GET_ENCOUNTER_DETAIL_SCOPED)
    params = _cypher_params(scope, patient_id, encounter_id=encounter_id)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **params)
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Encounter not found.")
    r = rows[0]
    coded_terms = [
        CodedTerm(
            code_id=t.get("code_id"),
            display=_strip_snomed_suffix(t.get("display") or t.get("code_id")),
            system=t.get("system") or "SNOMED",
            evidence=t.get("evidence"),
            evidence_sentence=t.get("evidence_sentence"),
            assertion=t.get("assertion"),
            confidence=(
                float(t["confidence"]) if t.get("confidence") is not None else None
            ),
            value=str(t["value"]) if t.get("value") is not None else None,
            unit=t.get("unit"),
        )
        for t in (r.get("coded_terms") or [])
        if t and (t.get("display") or t.get("code_id"))
    ]
    return EncounterDetail(
        encounter_id=r.get("encounter_id", encounter_id),
        encounter_date=r.get("encounter_date"),
        encounter_type=r.get("encounter_type") or "Encounter",
        specialty=r.get("specialty"),
        full_text=r.get("full_text") or "",
        episode_id=r.get("episode_id"),
        coded_terms=coded_terms,
    )


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentRow])
def get_patient_documents(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[DocumentRow]:
    """Document list with linked SBAR content for the document reader."""
    query = _pick_query(scope, GET_DOCUMENTS_ADMIN, GET_DOCUMENTS_SCOPED)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **_cypher_params(scope, patient_id))
    finally:
        client.close()
    results = []
    for r in rows:
        if not r.get("document_id"):
            continue
        sbar = None
        if r.get("sbar_id"):
            sbar = SbarContent(
                sbar_id=r["sbar_id"],
                status=r.get("sbar_status"),
                situation=r.get("sbar_situation"),
                background=r.get("sbar_background"),
                assessment=r.get("sbar_assessment"),
                recommendation=r.get("sbar_recommendation"),
            )
        results.append(
            DocumentRow(
                document_id=r["document_id"],
                document_date=r.get("document_date") or None,
                document_type=r.get("document_type") or "Document",
                title=r.get("title") or "Untitled",
                category=r.get("category") or None,
                text_preview=r.get("text_preview") or None,
                full_text=r.get("full_text") or "",
                content_type=r.get("content_type") or None,
                original_url=sign_patient_document_url(r.get("original_url") or None),
                markdown_url=sign_patient_document_url(r.get("markdown_url") or None),
                episode_id=r.get("episode_id"),
                episode_label=r.get("episode_label") or "General",
                folder_label=resolve_document_folder_label(
                    episode_label=r.get("episode_label") or "General",
                    clinic_type=r.get("clinic_type") or None,
                    referral_specialty=r.get("referral_specialty") or None,
                    service_name=r.get("service_name") or None,
                ),
                referral_id=r.get("referral_id") or None,
                chunk_count=int(r.get("chunk_count") or 0),
                sbar=sbar,
            )
        )
    return results


@router.get(
    "/patients/{patient_id}/assessments",
    response_model=list[AssessmentRow],
)
def get_patient_assessments(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[AssessmentRow]:
    """All SBAR assessments for a patient grouped by episode."""
    query = _pick_query(scope, GET_ASSESSMENTS_ADMIN, GET_ASSESSMENTS_SCOPED)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **_cypher_params(scope, patient_id))
    finally:
        client.close()
    return [
        AssessmentRow(
            assessment_id=r["assessment_id"],
            episode_id=r.get("episode_id"),
            episode_label=r.get("episode_label") or "Patient summary",
            scope=r.get("scope"),
            status=r.get("status"),
            created_at=r.get("created_at"),
            situation=r.get("situation"),
            background=r.get("background"),
            assessment=r.get("assessment"),
            recommendation=r.get("recommendation"),
            content=r.get("content"),
            stt=_coerce_optional_text(r.get("stt")),
            stt_evidence=r.get("stt_evidence"),
            completeness_failed_count=(
                int(r["completeness_failed_count"])
                if r.get("completeness_failed_count") is not None
                else None
            ),
            background_parts=_coerce_optional_text(r.get("background_parts")),
            completeness_result_json=_coerce_optional_text(
                r.get("completeness_result_json")
            ),
        )
        for r in rows
        if r.get("assessment_id")
    ]


@router.get("/patients/{patient_id}/alerts", response_model=list[AlertRow])
def get_patient_alerts(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[AlertRow]:
    """All safety alerts for a patient."""
    query = _pick_query(scope, GET_ALERTS_ADMIN, GET_ALERTS_SCOPED)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **_cypher_params(scope, patient_id))
    finally:
        client.close()
    return [
        AlertRow(
            alert_id=r["alert_id"],
            alert_type=r.get("alert_type") or "Alert",
            severity=r.get("severity") or "medium",
            created_at=r.get("created_at"),
            resolved_at=r.get("resolved_at"),
            message=r.get("message"),
            condition_context=r.get("condition_context"),
            guideline_ref=r.get("guideline_ref"),
        )
        for r in rows
        if r.get("alert_id")
    ]


@router.get(
    "/patients/{patient_id}/coded-entities",
    response_model=list[CodedEntityRow],
)
def get_patient_coded_entities(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> list[CodedEntityRow]:
    """Patient-level SNOMED coded entities: diseases, findings, situations, medications."""
    query = _pick_query(scope, GET_CODED_ENTITIES_ADMIN, GET_CODED_ENTITIES_SCOPED)
    client = PatientGraphClient()
    try:
        rows = client.run(query, **_cypher_params(scope, patient_id))
    finally:
        client.close()
    seen: set[str] = set()
    result = []
    for r in rows:
        if not r.get("name"):
            continue
        key = f"{r.get('entity_type')}:{r.get('concept_id') or r.get('name')}"
        if key in seen:
            continue
        seen.add(key)
        result.append(
            CodedEntityRow(
                entity_type=r["entity_type"],
                name=_strip_snomed_suffix(r["name"]) or r["name"],
                concept_id=r.get("concept_id"),
            )
        )
    return result


@router.get(
    "/patients/{patient_id}/episodes/{episode_id}/milestones",
    response_model=EpisodeMilestones,
)
def get_episode_milestones(
    patient_id: str,
    episode_id: str,
    scope: CallerScope = Depends(get_caller_scope),
) -> EpisodeMilestones:
    """Milestone dates for a single episode."""
    params = _cypher_params(scope, patient_id, episode_id=episode_id)
    client = PatientGraphClient()
    try:
        rows = client.run(GET_MILESTONES, **params)
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Episode not found.")
    r = rows[0]

    def _dates(raw: Any) -> list[str]:
        return [str(d)[:10] for d in (raw or []) if d]

    steps = [
        MilestoneStep(milestone_type="referral", dates=_dates(r.get("referral_dates"))),
        MilestoneStep(
            milestone_type="specialist_visit",
            dates=_dates(r.get("specialist_dates")),
        ),
        MilestoneStep(
            milestone_type="diagnosis", dates=_dates(r.get("diagnosis_dates"))
        ),
        MilestoneStep(milestone_type="outcome", dates=_dates(r.get("outcome_dates"))),
    ]
    return EpisodeMilestones(
        episode_id=r.get("episode_id", episode_id),
        referral_date=str(r["referral_date"])[:10] if r.get("referral_date") else None,
        end_date=str(r["end_date"])[:10] if r.get("end_date") else None,
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Alert action (PATCH)
# ---------------------------------------------------------------------------


class AlertAction(BaseModel):
    action: str  # "resolve" | "escalate" | "review"
    reviewed_by: Optional[str] = None


class AlertActionResult(BaseModel):
    alert_id: str
    alert_type: Optional[str] = None
    resolved_at: Optional[str] = None
    escalated_at: Optional[str] = None
    action: Optional[str] = None


@router.patch(
    "/patients/{patient_id}/alerts/{alert_id}",
    response_model=AlertActionResult,
)
def patch_alert(
    patient_id: str,
    alert_id: str,
    body: AlertAction,
    scope: CallerScope = Depends(get_caller_scope),
) -> AlertActionResult:
    """Mark an alert as reviewed, resolved, or escalated."""
    if body.action not in {"resolve", "escalate", "review"}:
        raise HTTPException(
            status_code=400, detail="action must be resolve, escalate, or review"
        )
    params = _cypher_params(
        scope,
        patient_id,
        alert_id=alert_id,
        action=body.action,
        reviewed_by=body.reviewed_by or "user",
    )
    client = PatientGraphClient()
    try:
        rows = client.run(PATCH_ALERT, **params)
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Alert not found.")
    r = rows[0]
    return AlertActionResult(
        alert_id=r["alert_id"],
        alert_type=r.get("alert_type"),
        resolved_at=r.get("resolved_at"),
        escalated_at=r.get("escalated_at"),
        action=r.get("action"),
    )
