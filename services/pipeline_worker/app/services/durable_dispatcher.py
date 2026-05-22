"""Dispatch durable workflow messages from the shared pipeline queue."""

from __future__ import annotations

import json
from typing import Any

from libs.message_bus.base import Message, MessageBusAdapter


def normalise_message_body(
    message: Message | dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    body: Any = message.body if isinstance(message, Message) else message
    if isinstance(body, (str, bytes)):
        body = json.loads(body)
    return body if isinstance(body, dict) else {}


def is_durable_message(body: dict[str, Any]) -> bool:
    from services.pipeline_worker.app.services.referral_durable_steps import (
        is_referral_durable_message,
        is_referral_durable_start,
    )

    return is_referral_durable_message(body) or is_referral_durable_start(body)


async def handle_durable_message(
    body: dict[str, Any],
    *,
    bus: MessageBusAdapter,
    publish_progress: Any | None = None,
    queue_name: str = "pipeline-jobs",
) -> bool:
    from services.pipeline_worker.app.services.referral_durable_steps import (
        handle_referral_durable_message,
        is_referral_durable_message,
        is_referral_durable_start,
        start_referral_durable_workflow,
    )
    from services.pipeline_worker.app.services.sbar_orchestrator import (
        handle_sbar_message,
    )

    if is_referral_durable_start(body):
        await start_referral_durable_workflow(body, bus=bus, queue_name=queue_name)
        return True
    if is_referral_durable_message(body):
        await handle_referral_durable_message(
            body,
            bus=bus,
            publish_progress=publish_progress,
            queue_name=queue_name,
        )
        return True
    if body.get("event_type") == "sbar_requested":
        await handle_sbar_message(body)
        return True
    return False
