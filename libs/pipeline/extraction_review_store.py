"""Persist and resume extraction-quality review tasks.

Atlas trace:
  DI: DI-4A012A59
  DO: DO-E7824FED
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from libs.cypher.extraction_review_queries import (
    CANCEL_EXTRACTION_REVIEW_TASK,
    CANCEL_PAUSED_EXTRACTION_STAGE,
    CREATE_EXTRACTION_REVIEW_TASK,
    GET_EXTRACTION_REVIEW_TASK,
    GET_REFERRAL_BY_PATIENT,
    GET_REFERRAL_BY_PATIENT_UBRN,
    GET_REVIEW_IDENTIFIERS,
    GET_RUN_CASE_ID,
    RESOLVE_EXTRACTION_REVIEW_TASK,
    RESET_PAUSED_EXTRACTION_FOR_RERUN,
    SUPERSEDE_EXTRACTION_REVIEW_TASK,
    UNLOCK_PAUSED_EXTRACTION_STAGE,
)
from libs.clinical_scoping.healthcare_service import resolve_healthcare_service
from libs.pipeline.extraction_review_ids import (
    extract_review_identifiers,
    format_nhs_number,
    format_ubrn,
)
from libs.pipeline.document_quality import DocumentQuality, form_fingerprint
from libs.pipeline.extraction_learning_store import persist_review_learning
from libs.pipeline.extraction_quality_gate import (
    build_review_task,
    complete_extraction_review,
)
from libs.pipeline.extraction_review_letter import resolve_review_letter

DURABLE_STEP_EVENT = "durable_step"
VALID_CANCEL_REASONS = frozenset({"duplicate", "created_in_error", "no_longer_needed"})


@dataclass(frozen=True)
class PersistReviewRequest:
    run_id: str
    patient_id: str
    plan_definition_id: str
    step_id: str
    next_action_id: str
    quality: DocumentQuality
    draft_entities: list[dict[str, Any]]
    source_text: str = ""
    form_recognition: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class RerunExtractionResult:
    run_id: str
    step_id: str
    published: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step_id": self.step_id,
            "published": self.published,
        }


@dataclass(frozen=True)
class CancelResult:
    status: str
    reason: str
    taught: bool = False
    resumed: bool = False
    already_cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "taught": self.taught,
            "resumed": self.resumed,
            "already_cancelled": self.already_cancelled,
        }


@dataclass(frozen=True)
class ResumePlan:
    entities: list[dict[str, Any]]
    few_shot: dict[str, Any]
    form_fingerprint_id: str
    next_event_type: str
    next_step_id: str
    publish: bool
    already_resumed: bool


def persist_extraction_review_task(req: PersistReviewRequest) -> dict[str, Any]:
    draft = list(req.draft_entities or [])
    task = build_review_task(
        run_id=req.run_id,
        patient_id=req.patient_id,
        quality=req.quality,
        draft_entities=draft,
    )
    task["task_id"] = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"extraction-quality:{req.run_id}")
    )
    task["plan_definition_id"] = req.plan_definition_id
    task["step_id"] = req.step_id
    task["next_action_id"] = req.next_action_id
    task["draft_entities_json"] = json.dumps(draft, ensure_ascii=True)
    quality = req.quality.to_dict()
    if req.form_recognition:
        quality["form_recognition"] = list(req.form_recognition)
    task["document_quality_json"] = json.dumps(quality, ensure_ascii=True, default=str)
    task["source_text"] = req.source_text or ""
    return task


def write_extraction_review_task(client: Any, task: dict[str, Any]) -> None:
    client.run(
        CREATE_EXTRACTION_REVIEW_TASK,
        task_id=task["task_id"],
        run_id=task["run_id"],
        patient_id=task.get("patient_id") or "",
        plan_definition_id=task.get("plan_definition_id") or "",
        step_id=task.get("step_id") or "",
        next_action_id=task.get("next_action_id") or "",
        reason=task.get("reason") or "low_document_quality",
        draft_entities_json=task.get("draft_entities_json") or "[]",
        document_quality_json=task.get("document_quality_json") or "{}",
        source_text=task.get("source_text") or "",
    )


def plan_extraction_resume(
    *,
    task: dict[str, Any],
    source_text: str,
    reviewed_entities: list[dict[str, Any]],
    already_resumed: bool,
) -> ResumePlan:
    complete = complete_extraction_review(
        source_text=source_text,
        draft_entities=[],
        reviewed_entities=reviewed_entities,
    )
    next_step = str(task.get("next_action_id") or "")
    if already_resumed:
        return ResumePlan(
            entities=complete.entities,
            few_shot=complete.few_shot,
            form_fingerprint_id=complete.form_fingerprint_id,
            next_event_type=DURABLE_STEP_EVENT,
            next_step_id=next_step,
            publish=False,
            already_resumed=True,
        )
    return ResumePlan(
        entities=complete.entities,
        few_shot=complete.few_shot,
        form_fingerprint_id=complete.form_fingerprint_id,
        next_event_type=DURABLE_STEP_EVENT,
        next_step_id=next_step,
        publish=True,
        already_resumed=False,
    )


def build_resume_message(task: dict[str, Any]) -> dict[str, Any]:
    next_id = str(task.get("next_action_id") or "")
    plan_id = str(task.get("plan_definition_id") or "")
    return {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": next_id,
        "step_id": next_id,
        "run_id": str(task.get("run_id") or ""),
        "patient_id": str(task.get("patient_id") or ""),
        "plan_definition_id": plan_id,
        "workflow_id": plan_id,
    }


def build_rerun_extraction_message(task: dict[str, Any]) -> dict[str, Any]:
    step_id = str(task.get("step_id") or "")
    plan_id = str(task.get("plan_definition_id") or "")
    return {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": step_id,
        "step_id": step_id,
        "run_id": str(task.get("run_id") or ""),
        "patient_id": str(task.get("patient_id") or ""),
        "plan_definition_id": plan_id,
        "workflow_id": plan_id,
    }


def _load_task(client: Any, task_id: str) -> dict[str, Any]:
    rows = client.run(GET_EXTRACTION_REVIEW_TASK, task_id=task_id)
    row = (rows or [None])[0]
    if not row:
        raise ValueError(f"review task {task_id!r} not found")
    return dict(row)


def _unlock_stage(client: Any, task: dict[str, Any], plan: ResumePlan) -> None:
    quality = task.get("document_quality_json") or "{}"
    output = {
        "entities": plan.entities,
        "extraction_gate": "reviewed",
        "document_quality": json.loads(quality) if quality else {},
    }
    rows = client.run(
        UNLOCK_PAUSED_EXTRACTION_STAGE,
        run_id=task.get("run_id") or "",
        step_id=task.get("step_id") or "",
        output_json=json.dumps(output, ensure_ascii=True, default=str),
        next_action_ids_json=json.dumps([plan.next_step_id], ensure_ascii=True),
    )
    if not rows:
        raise ValueError("paused extraction stage not found")


def load_extraction_review_detail(
    client: Any,
    task_id: str,
    *,
    store: Any | None = None,
) -> dict[str, Any]:
    task = _load_task(client, task_id)
    draft_raw = task.get("draft_entities_json") or "[]"
    quality_raw = task.get("document_quality_json") or "{}"
    stage_store = store
    if stage_store is None:
        from libs.workflow.pipeline_stage_store import PipelineStageStore

        stage_store = PipelineStageStore(client)
    state = stage_store.load_accumulated_state(str(task.get("run_id") or ""))
    letter = resolve_review_letter(
        client=client,
        task=task,
        state=state or {},
    )
    graph_nhs, graph_ubrn = _load_graph_identifiers(
        client, str(task.get("patient_id") or "")
    )
    ids = extract_review_identifiers(
        letter,
        graph_nhs_number=graph_nhs,
        graph_ubrn=graph_ubrn,
    )
    run_id = task.get("run_id") or ""
    patient_id = str(task.get("patient_id") or "")
    organization_id = str((state or {}).get("healthcare_service_org_id") or "")
    service_id = str((state or {}).get("healthcare_service_id") or "")
    organization_name = str((state or {}).get("healthcare_service_org_name") or "")
    service_name = str((state or {}).get("healthcare_service_name") or "")
    if not organization_id or not service_id:
        org_svc = _load_org_service_from_graph(
            client,
            run_id=run_id,
            patient_id=patient_id,
            referral_id=str(
                (state or {}).get("referral_id") or (state or {}).get("case_id") or ""
            ),
            ubrn=ids.ubrn,
        )
        organization_id = organization_id or org_svc.get("organization_id") or ""
        service_id = service_id or org_svc.get("service_id") or ""
        organization_name = organization_name or org_svc.get("organization_name") or ""
        service_name = service_name or org_svc.get("service_name") or ""
    quality = json.loads(quality_raw) if quality_raw else {}
    fp_hash = form_fingerprint(letter)
    return {
        "task_id": task.get("task_id") or task_id,
        "run_id": run_id,
        "patient_id": patient_id,
        "status": task.get("status") or "",
        "reason": task.get("reason") or "",
        "draft_entities": json.loads(draft_raw) if draft_raw else [],
        "document_quality": quality,
        "form_recognition": list(quality.get("form_recognition") or []),
        "form_fingerprint": fp_hash,
        "source_text": letter,
        "nhs_number": format_nhs_number(ids.nhs_number),
        "ubrn": format_ubrn(ids.ubrn),
        "organization_id": str(organization_id),
        "organization_name": str(organization_name),
        "service_id": str(service_id),
        "service_name": str(service_name),
    }


def _load_org_service_from_graph(
    client: Any,
    *,
    run_id: str,
    patient_id: str = "",
    referral_id: str = "",
    ubrn: str = "",
) -> dict[str, str]:
    """Resolve org and service via ReferralRequest -> Service graph path.

    Used when accumulated pipeline state lacks healthcare_service_* fields.
    """
    resolved_referral_id = _resolve_referral_id_for_run(
        client,
        run_id=run_id,
        patient_id=patient_id,
        referral_id=referral_id,
        ubrn=ubrn,
    )
    if not resolved_referral_id:
        return {}
    service = resolve_healthcare_service(
        client,
        source_node_type="ReferralRequest",
        source_node_id=resolved_referral_id,
    )
    if service is None:
        return {}
    return {
        "organization_id": service.organization_id or "",
        "organization_name": service.organization_name or "",
        "service_id": service.id,
        "service_name": service.name,
    }


def _resolve_referral_id_for_run(
    client: Any,
    *,
    run_id: str,
    patient_id: str,
    referral_id: str,
    ubrn: str,
) -> str:
    explicit = str(referral_id or "").strip()
    if explicit:
        return explicit
    if run_id:
        rows = client.run(GET_RUN_CASE_ID, run_id=run_id)
        case_id = str((rows or [{}])[0].get("case_id") or "").strip()
        if case_id:
            return case_id
    patient = str(patient_id or "").strip()
    if not patient:
        return ""
    ubrn_text = str(ubrn or "").strip()
    if ubrn_text:
        rows = client.run(
            GET_REFERRAL_BY_PATIENT_UBRN,
            patient_id=patient,
            ubrn=ubrn_text,
        )
        matched = str((rows or [{}])[0].get("referral_id") or "").strip()
        if matched:
            return matched
    rows = client.run(GET_REFERRAL_BY_PATIENT, patient_id=patient)
    return str((rows or [{}])[0].get("referral_id") or "").strip()


def _load_graph_identifiers(client: Any, patient_id: str) -> tuple[str, str]:
    if not patient_id:
        return "", ""
    rows = client.run(GET_REVIEW_IDENTIFIERS, patient_id=patient_id)
    row = (rows or [{}])[0] or {}
    return str(row.get("nhs_number") or ""), str(row.get("ubrn") or "")


def resume_extraction_review(
    client: Any,
    *,
    task_id: str,
    source_text: str,
    reviewed_entities: list[dict[str, Any]],
    publish: Callable[[dict[str, Any]], None],
    resolved_by: str = "unknown",
) -> ResumePlan:
    task = _load_task(client, task_id)
    already = str(task.get("status") or "") == "resolved" or bool(
        task.get("resumed_at")
    )
    plan = plan_extraction_resume(
        task=task,
        source_text=source_text,
        reviewed_entities=reviewed_entities,
        already_resumed=already,
    )
    if not plan.publish:
        return plan
    _unlock_stage(client, task, plan)
    publish(build_resume_message(task))
    _persist_learned_form(plan)
    client.run(
        RESOLVE_EXTRACTION_REVIEW_TASK,
        task_id=task_id,
        resolved_by=resolved_by,
    )
    return plan


def rerun_paused_extraction(
    client: Any,
    *,
    task_id: str,
    publish: Callable[[dict[str, Any]], None],
    triggered_by: str = "unknown",
) -> RerunExtractionResult:
    """Re-queue act-ref-extract after a taught :FormSchema is saved."""
    task = _load_task(client, task_id)
    status = str(task.get("status") or "")
    if status != "pending":
        raise ValueError(f"review task {task_id!r} is not pending")
    run_id = str(task.get("run_id") or "")
    step_id = str(task.get("step_id") or "")
    if not run_id or not step_id:
        raise ValueError("review task is missing run_id or step_id")
    rows = client.run(
        RESET_PAUSED_EXTRACTION_FOR_RERUN,
        run_id=run_id,
        step_id=step_id,
    )
    if not rows:
        raise ValueError("paused extraction stage not found")
    superseded = client.run(
        SUPERSEDE_EXTRACTION_REVIEW_TASK,
        task_id=task_id,
        triggered_by=triggered_by,
    )
    if not superseded:
        raise ValueError("review task is not pending")
    message = build_rerun_extraction_message(task)
    publish(message)
    return RerunExtractionResult(run_id=run_id, step_id=step_id, published=True)


def _persist_learned_form(plan: ResumePlan) -> None:
    persist_review_learning(
        fingerprint_name=f"learned-{plan.form_fingerprint_id}",
        fingerprint=plan.form_fingerprint_id,
        few_shot=plan.few_shot,
    )


def cancel_extraction_review(
    client: Any,
    *,
    task_id: str,
    reason: str,
    cancelled_by: str = "unknown",
) -> CancelResult:
    if reason not in VALID_CANCEL_REASONS:
        raise ValueError("invalid cancel reason")
    task = _load_task(client, task_id)
    status = str(task.get("status") or "")
    if status == "cancelled":
        return CancelResult(
            status="cancelled",
            reason=reason,
            already_cancelled=True,
        )
    if status != "pending":
        raise ValueError(f"review task {task_id!r} is not pending")
    _write_cancel(client, task, reason, cancelled_by)
    return CancelResult(status="cancelled", reason=reason)


def _write_cancel(
    client: Any,
    task: dict[str, Any],
    reason: str,
    cancelled_by: str,
) -> None:
    rows = client.run(
        CANCEL_EXTRACTION_REVIEW_TASK,
        task_id=task.get("task_id") or "",
        reason=reason,
        cancelled_by=cancelled_by,
    )
    if not rows:
        raise ValueError("review task is not pending")
    client.run(
        CANCEL_PAUSED_EXTRACTION_STAGE,
        run_id=task.get("run_id") or "",
        step_id=task.get("step_id") or "",
    )
