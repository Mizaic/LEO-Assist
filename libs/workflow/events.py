"""Event handler classes for dispatching workflow events from various sources.

Atlas trace:
  DO: DO-4641EEE1
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4641EEE1")
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING, Callable

from libs.message_bus.base import Message

if TYPE_CHECKING:
    from libs.workflow.engine import WorkflowEngine

logger = logging.getLogger(__name__)


@dataclass
class WorkflowEventEnvelope:
    event_type: str
    patient_id: str
    encounter_id: str | None = None
    plan_definition_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ServiceBusEventHandler:
    """Handles events from the Azure Service Bus pipeline-jobs queue."""

    def __init__(self, engine: "WorkflowEngine"):
        self._engine = engine

    async def handle_message(
        self,
        message: Message | dict[str, Any] | str | bytes,
        *,
        step_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Handle a Service Bus message preserving correlation/run identity."""
        correlation_id: str | None = None
        if isinstance(message, Message):
            message_body = message.body
            correlation_id = message.correlation_id
        else:
            message_body = message
        body = (
            json.loads(message_body)
            if isinstance(message_body, (str, bytes))
            else message_body
        )
        run_id = str(
            correlation_id
            or body.get("run_id")
            or body.get("message_id")
            or uuid.uuid4()
        )
        event = WorkflowEventEnvelope(
            event_type=body.get("event_type", "unknown"),
            patient_id=body.get("patient_id", ""),
            encounter_id=body.get("encounter_id"),
            plan_definition_id=body.get("plan_definition_id"),
            context=body.get("context", {}),
            run_id=run_id,
        )
        logger.info(
            "Handling Service Bus event: %s for patient %s",
            event.event_type,
            event.patient_id,
        )
        return await self._engine.handle_event(event, step_callback=step_callback)


class WebhookEventHandler:
    """Handles events from external system webhooks (NHS, Labs, etc.)."""

    def __init__(self, engine: "WorkflowEngine"):
        self._engine = engine

    async def handle_lab_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = WorkflowEventEnvelope(
            event_type="new-result",
            patient_id=payload.get("patient_id", ""),
            context={"result_data": payload},
        )
        return await self._engine.handle_event(event)

    async def handle_referral_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = WorkflowEventEnvelope(
            event_type="referral-response",
            patient_id=payload.get("patient_id", ""),
            context={"referral_data": payload},
        )
        return await self._engine.handle_event(event)


class TimerEventHandler:
    """Handles scheduled timer events from Service Bus."""

    def __init__(self, engine: "WorkflowEngine"):
        self._engine = engine

    async def handle_timer(self, message_body: str | bytes) -> dict[str, Any]:
        body = (
            json.loads(message_body)
            if isinstance(message_body, (str, bytes))
            else message_body
        )
        event = WorkflowEventEnvelope(
            event_type="timer",
            patient_id=body.get("patient_id", ""),
            plan_definition_id=body.get("plan_definition_id"),
            context=body.get("context", {}),
        )
        logger.info("Handling timer event for patient %s", event.patient_id)
        return await self._engine.handle_event(event)
