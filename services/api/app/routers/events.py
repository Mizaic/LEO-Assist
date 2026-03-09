"""External event webhook endpoints and clinician action events.

Receives events from external systems (lab results, referral responses)
and clinician UI actions, transforms them into PipelineJobMessages, and
publishes to the pipeline-jobs Service Bus queue.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])

PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")


class LabResultPayload(BaseModel):
    patient_id: str
    test_code: str | None = None
    result_value: str | None = None
    result_unit: str | None = None
    reference_range: str | None = None
    status: str | None = None
    source_system: str | None = None


class ReferralResponsePayload(BaseModel):
    patient_id: str
    referral_id: str | None = None
    status: str | None = None
    response_date: str | None = None
    source_system: str | None = None


class ClinicianActionPayload(BaseModel):
    patient_id: str
    encounter_id: str | None = None
    action_type: str
    plan_definition_id: str | None = None
    context: dict[str, Any] | None = None


class PipelineJobMessage(BaseModel):
    patient_id: str
    encounter_id: str | None = None
    event_type: str
    plan_definition_id: str | None = None
    context: dict[str, Any] = {}


async def _publish_to_pipeline(message: PipelineJobMessage) -> dict[str, str]:
    """Publish a pipeline job message to the Service Bus queue."""
    try:
        from libs.message_bus.factory import create_message_bus
        from libs.message_bus.base import Message
        bus = create_message_bus()
        await bus.send(
            PIPELINE_QUEUE,
            Message(
                body=message.model_dump(),
                correlation_id=message.patient_id,
                subject=message.event_type,
            ),
        )
        await bus.close()
        return {"status": "queued", "event_type": message.event_type}
    except Exception as exc:
        logger.error("Failed to publish pipeline job: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Event queue unavailable") from exc


@router.post("/lab-result")
async def receive_lab_result(payload: LabResultPayload) -> dict[str, str]:
    """Receive a lab result notification from an external system."""
    logger.info(
        "Lab result received for patient %s (test=%s)",
        payload.patient_id, payload.test_code,
    )
    message = PipelineJobMessage(
        patient_id=payload.patient_id,
        event_type="new-result",
        context={"result_data": payload.model_dump()},
    )
    return await _publish_to_pipeline(message)


@router.post("/referral-response")
async def receive_referral_response(payload: ReferralResponsePayload) -> dict[str, str]:
    """Receive a referral response from eRS or another system."""
    logger.info(
        "Referral response received for patient %s (referral=%s)",
        payload.patient_id, payload.referral_id,
    )
    message = PipelineJobMessage(
        patient_id=payload.patient_id,
        event_type="referral-response",
        context={"referral_data": payload.model_dump()},
    )
    return await _publish_to_pipeline(message)


@router.post("/clinician-action")
async def receive_clinician_action(payload: ClinicianActionPayload) -> dict[str, str]:
    """Receive a clinician decision from the Primary Care UI."""
    logger.info(
        "Clinician action: %s for patient %s",
        payload.action_type, payload.patient_id,
    )
    message = PipelineJobMessage(
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        event_type="clinician-action",
        plan_definition_id=payload.plan_definition_id,
        context={
            "action_type": payload.action_type,
            **(payload.context or {}),
        },
    )
    return await _publish_to_pipeline(message)


@router.post("/timer")
async def schedule_timer_event(
    patient_id: str,
    plan_definition_id: str,
    action_id: str,
    delay_seconds: int = 86400,
) -> dict[str, str]:
    """Schedule a safety net timer event for future delivery."""
    logger.info(
        "Scheduling timer for patient %s, action %s in %ds",
        patient_id, action_id, delay_seconds,
    )
    try:
        from libs.message_bus.factory import create_message_bus
        from libs.message_bus.base import Message
        bus = create_message_bus()
        message = Message(
            body={
                "patient_id": patient_id,
                "event_type": "timer",
                "plan_definition_id": plan_definition_id,
                "context": {"timer_action_id": action_id},
            },
            correlation_id=patient_id,
            subject="timer",
        )
        await bus.send(
            PIPELINE_QUEUE,
            message,
            schedule_after_seconds=delay_seconds,
        )
        await bus.close()
        return {"status": "scheduled", "delay_seconds": str(delay_seconds)}
    except Exception as exc:
        logger.error("Failed to schedule timer: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Timer scheduling unavailable") from exc
