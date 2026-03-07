"""Event handler classes for dispatching workflow events from various sources."""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.workflow.engine import WorkflowEngine, WorkflowEvent

logger = logging.getLogger(__name__)


class ServiceBusEventHandler:
    """Handles events from the Azure Service Bus pipeline-jobs queue."""

    def __init__(self, engine: WorkflowEngine):
        self._engine = engine

    async def handle_message(self, message_body: str | bytes) -> dict[str, Any]:
        body = json.loads(message_body) if isinstance(message_body, (str, bytes)) else message_body
        event = WorkflowEvent(
            event_type=body.get("event_type", "unknown"),
            patient_id=body.get("patient_id", ""),
            encounter_id=body.get("encounter_id"),
            plan_definition_id=body.get("plan_definition_id"),
            context=body.get("context", {}),
        )
        logger.info("Handling Service Bus event: %s for patient %s", event.event_type, event.patient_id)
        return await self._engine.handle_event(event)


class WebhookEventHandler:
    """Handles events from external system webhooks (NHS, Labs, etc.)."""

    def __init__(self, engine: WorkflowEngine):
        self._engine = engine

    async def handle_lab_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = WorkflowEvent(
            event_type="new-result",
            patient_id=payload.get("patient_id", ""),
            context={"result_data": payload},
        )
        return await self._engine.handle_event(event)

    async def handle_referral_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = WorkflowEvent(
            event_type="referral-response",
            patient_id=payload.get("patient_id", ""),
            context={"referral_data": payload},
        )
        return await self._engine.handle_event(event)


class TimerEventHandler:
    """Handles scheduled timer events from Service Bus."""

    def __init__(self, engine: WorkflowEngine):
        self._engine = engine

    async def handle_timer(self, message_body: str | bytes) -> dict[str, Any]:
        body = json.loads(message_body) if isinstance(message_body, (str, bytes)) else message_body
        event = WorkflowEvent(
            event_type="timer",
            patient_id=body.get("patient_id", ""),
            plan_definition_id=body.get("plan_definition_id"),
            context=body.get("context", {}),
        )
        logger.info("Handling timer event for patient %s", event.patient_id)
        return await self._engine.handle_event(event)
