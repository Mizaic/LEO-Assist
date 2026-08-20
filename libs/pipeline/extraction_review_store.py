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
    CREATE_EXTRACTION_REVIEW_TASK,
    GET_EXTRACTION_REVIEW_TASK,
    RESOLVE_EXTRACTION_REVIEW_TASK,
    UNLOCK_PAUSED_EXTRACTION_STAGE,
)
from libs.pipeline.document_quality import DocumentQuality
from libs.pipeline.extraction_learning_store import persist_review_learning
from libs.pipeline.extraction_quality_gate import (
    build_review_task,
    complete_extraction_review,
)

DURABLE_STEP_EVENT = "durable_step"


@dataclass(frozen=True)
class PersistReviewRequest:
    run_id: str
    patient_id: str
    plan_definition_id: str
    step_id: str
    next_action_id: str
    quality: DocumentQuality
    draft_entities: list[dict[str, Any]]


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
    task["document_quality_json"] = json.dumps(req.quality.to_dict(), ensure_ascii=True)
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
    return {
        "task_id": task.get("task_id") or task_id,
        "run_id": task.get("run_id") or "",
        "patient_id": task.get("patient_id") or "",
        "status": task.get("status") or "",
        "reason": task.get("reason") or "",
        "draft_entities": json.loads(draft_raw) if draft_raw else [],
        "document_quality": json.loads(quality_raw) if quality_raw else {},
        "source_text": str((state or {}).get("encounter_text") or ""),
    }


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


def _persist_learned_form(plan: ResumePlan) -> None:
    persist_review_learning(
        fingerprint_name=f"learned-{plan.form_fingerprint_id}",
        fingerprint=plan.form_fingerprint_id,
        few_shot=plan.few_shot,
    )
