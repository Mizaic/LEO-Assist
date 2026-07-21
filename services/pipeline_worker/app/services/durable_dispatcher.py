"""Dispatch durable workflow messages from the shared pipeline queue.

Atlas trace:
  DO: DO-C2F6CA16
  DI: DI-06CB6881
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C2F6CA16")

Routing rules:

1. DURABLE_STEP_EVENT in-flight messages -- always routed to DurableStepRunner
   regardless of the feature flag (a partially-started pipeline must finish).

2. Trigger events (event_type set, no action_id) for plans where
   is_durable_runner_enabled() is True -- routed to DurableStepRunner.start().

3. All other recognised durable messages return False.

Legacy referral_durable_steps.py handlers have been removed.  The referral
assessment plan (pd-referral-assessment) is now fully served by
DurableStepRunner.  Set DURABLE_ENGINE_ENABLED=true (all plans) or
DURABLE_ENGINE_ENABLED=referral (referral only) to enable in production.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.message_bus.base import Message, MessageBusAdapter
from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    is_durable_runner_enabled,
)

logger = logging.getLogger(__name__)


def normalise_message_body(
    message: Message | dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    body: Any = message.body if isinstance(message, Message) else message
    if isinstance(body, (str, bytes)):
        body = json.loads(body)
    return body if isinstance(body, dict) else {}


def _plan_id_from_body(body: dict[str, Any]) -> str:
    return str(
        body.get("plan_definition_id")
        or body.get("workflow_id")
        or ""
    )


def is_durable_message(body: dict[str, Any]) -> bool:
    event_type = str(body.get("event_type") or "")
    # In-flight durable_step messages are always durable.
    if event_type == DURABLE_STEP_EVENT and body.get("action_id"):
        return True
    # Trigger events for runner-enabled plans are durable.
    plan_id = _plan_id_from_body(body)
    if event_type and event_type != DURABLE_STEP_EVENT and not body.get("action_id"):
        if is_durable_runner_enabled(plan_id):
            return True
    return False


async def handle_durable_message(
    body: dict[str, Any],
    *,
    bus: MessageBusAdapter,
    publish_progress: Any | None = None,
    queue_name: str = "pipeline-jobs",
) -> bool:
    event_type = str(body.get("event_type") or "")
    action_id = str(body.get("action_id") or "")
    plan_id = _plan_id_from_body(body)

    # In-flight durable_step messages -- always handled by DurableStepRunner.
    if event_type == DURABLE_STEP_EVENT and action_id:
        from libs.workflow.durable_step_runner import DurableStepRunner

        await DurableStepRunner.run_step(
            body,
            bus=bus,
            publish_progress=publish_progress,
            queue_name=queue_name,
        )
        return True

    # Trigger events for runner-enabled plans.
    if (
        event_type
        and event_type != DURABLE_STEP_EVENT
        and not action_id
        and is_durable_runner_enabled(plan_id)
    ):
        from libs.workflow.durable_step_runner import DurableStepRunner

        await DurableStepRunner.start(body, bus=bus, queue_name=queue_name)
        return True

    logger.debug(
        "handle_durable_message: no handler matched event_type=%s plan_id=%s",
        event_type,
        plan_id,
    )
    return False
