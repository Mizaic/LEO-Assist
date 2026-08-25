"""Complete a paused extraction review and unlock the referral.

Atlas trace:
  DI: DI-4A012A59
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline.extraction_learning_store import ensure_learning_writers
from libs.pipeline.extraction_review_store import (
    load_extraction_review_detail,
    resume_extraction_review,
)
from libs.pipeline.span_few_shot import save_span_few_shot

router = APIRouter(prefix="/operations", tags=["operations"])
_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")


class CompleteExtractionReviewRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    source_text: str = ""
    reviewed_entities: list[dict[str, Any]] = Field(default_factory=list)
    resolved_by: str = "unknown"


class SpanFewShotRequest(BaseModel):
    span: str = Field(..., min_length=1)
    letter: str = ""
    semantic_tag: str = "finding"
    assertion: str = "present"


async def _publish_resume(message: dict[str, Any]) -> None:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    bus = create_message_bus()
    await bus.send(
        _PIPELINE_QUEUE,
        Message(
            body=message,
            message_id=f"resume-{message.get('run_id')}-{message.get('action_id')}",
            correlation_id=str(message.get("run_id") or ""),
            subject=str(message.get("event_type") or "durable_step"),
        ),
    )


@router.get("/extraction-reviews/{task_id}")
def get_review(
    task_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    _ = scope
    client = PatientGraphClient()
    try:
        return load_extraction_review_detail(client, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()


@router.post("/extraction-reviews/complete")
async def complete_review(
    body: CompleteExtractionReviewRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    _ = scope
    if not body.reviewed_entities:
        raise HTTPException(status_code=400, detail="reviewed_entities is required")
    queued: list[dict[str, Any]] = []
    ensure_learning_writers()
    client = PatientGraphClient()
    try:
        result = resume_extraction_review(
            client,
            task_id=body.task_id,
            source_text=body.source_text,
            reviewed_entities=body.reviewed_entities,
            publish=queued.append,
            resolved_by=body.resolved_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        client.close()
    if result.publish:
        for message in queued:
            await _publish_resume(message)
    return {
        "entities": result.entities,
        "few_shot": result.few_shot,
        "form_fingerprint_id": result.form_fingerprint_id,
        "resume_once": result.publish,
        "already_resumed": result.already_resumed,
        "next_event_type": result.next_event_type,
        "next_step_id": result.next_step_id,
        "resolved_by": body.resolved_by,
    }


@router.post("/extraction-reviews/few-shot")
def save_few_shot(
    body: SpanFewShotRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    _ = scope
    try:
        return save_span_few_shot(
            span=body.span,
            letter=body.letter,
            semantic_tag=body.semantic_tag,
            assertion=body.assertion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
