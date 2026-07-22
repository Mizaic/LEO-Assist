"""Dispatch durable workflow messages from the shared pipeline queue.

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-CE65B1F2")

Routing rules:

1. DURABLE_STEP_EVENT in-flight messages -- always routed to DurableStepRunner
   regardless of the feature flag (a partially-started pipeline must finish).

2. Trigger events (event_type set, no action_id) for plans where
   is_durable_runner_enabled() is True -- routed to DurableStepRunner.start().

3. All other recognised durable messages return False.

Legacy referral_durable_steps.py handlers have been removed. Plans with
``workflowMode: durable_pubsub`` (for example pd-referral-assessment and
pd-gp-encounter-coding) are admitted via pinned PlanDefinitionVersion snapshots.
Set ``DURABLE_ENGINE_DISABLED=true`` only to block new durable runs in an
emergency rollback.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.message_bus.base import Message, MessageBusAdapter
from libs.message_bus.settlement import (
    enforce_durable_step_settlement,
    validate_pipeline_lease_config,
)
from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    is_durable_runner_enabled,
)

logger = logging.getLogger(__name__)
_lease_config_logged = False


def _log_lease_config_once() -> None:
    global _lease_config_logged
    if _lease_config_logged:
        return
    _lease_config_logged = True
    for warning in validate_pipeline_lease_config():
        logger.warning("pipeline lease config: %s", warning)


def normalise_message_body(
    message: Message | dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    body: Any = message.body if isinstance(message, Message) else message
    if isinstance(body, (str, bytes)):
        body = json.loads(body)
    return body if isinstance(body, dict) else {}


def _plan_id_from_body(body: dict[str, Any]) -> str:
    return str(body.get("plan_definition_id") or body.get("workflow_id") or "")


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

        _log_lease_config_once()
        result = await DurableStepRunner.run_step(
            body,
            bus=bus,
            publish_progress=publish_progress,
            queue_name=queue_name,
        )
        enforce_durable_step_settlement(
            result,
            message_id=str(body.get("_message_id") or ""),
            run_id=str(body.get("run_id") or ""),
            action_id=action_id,
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
