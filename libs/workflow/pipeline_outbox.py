"""Edge outbox helpers and dispatcher (D1.10 / D1.11).

Atlas trace:
  DI: DI-4976171D
  DO: DO-3A657CCF
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-4976171D")
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from libs.message_bus.base import Message, MessageBusAdapter
from libs.workflow.durable_steps import StepRequest

logger = logging.getLogger(__name__)


def build_edge_version(edge: dict[str, Any]) -> str:
    """Stable hash for a plan edge (source handle + target handles)."""
    parts = [
        str(edge.get("actionId") or edge.get("source") or ""),
        str(edge.get("sourceHandle") or ""),
        str(edge.get("targetHandle") or ""),
        str(edge.get("target") or ""),
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_outbox_event_id(
    run_id: str,
    stage_run_id: str,
    target_action_id: str,
    edge_version: str,
) -> str:
    raw = f"{run_id}:{stage_run_id}:{target_action_id}:{edge_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_durable_step_message_id(
    run_id: str,
    stage_run_id: str,
    target_action_id: str,
    edge_version: str,
) -> str:
    raw = f"msg:{run_id}:{stage_run_id}:{target_action_id}:{edge_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_first_step_message_id(run_id: str, action_id: str) -> str:
    """Deterministic Service Bus message_id for the first durable step."""
    raw = f"msg:first:{run_id}:{action_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_successor_outbox_events(
    request: StepRequest,
    *,
    stage_run_id: str,
    next_action_ids: list[str],
    successor_edges: list[dict[str, Any]],
    queue_name: str,
    body_template: dict[str, Any],
    repair_generation: int = 0,
) -> list[dict[str, str]]:
    """Build pending outbox rows for each successor edge.

    ``repair_generation`` > 0 mints new event/message ids so a sent-orphan
    successor can be re-queued after Service Bus drop/dedupe without
    colliding with the original deterministic ids.
    """
    edge_by_target: dict[str, dict[str, Any]] = {}
    for edge in successor_edges:
        target = str(edge.get("target") or "")
        if target:
            edge_by_target[target] = edge
    events: list[dict[str, str]] = []
    for target in next_action_ids:
        edge = edge_by_target.get(
            target, {"target": target, "actionId": request.step_id}
        )
        edge_version = build_edge_version(edge)
        if repair_generation > 0:
            edge_version = f"{edge_version}:r{repair_generation}"
        event_id = build_outbox_event_id(
            request.run_id, stage_run_id, target, edge_version
        )
        message_id = build_durable_step_message_id(
            request.run_id,
            stage_run_id,
            target,
            edge_version,
        )
        body = {**body_template, "action_id": target, "step_id": target}
        events.append(
            {
                "id": event_id,
                "target_action_id": target,
                "edge_version": edge_version,
                "message_id": message_id,
                "queue_name": queue_name,
                "body_json": json.dumps(body, default=str, sort_keys=True),
                "status": "pending",
            }
        )
    return events


async def dispatch_stage_outbox(
    store: Any,
    bus: MessageBusAdapter,
    request: StepRequest,
) -> int:
    """Send pending outbox events for a stage; claim each row before send."""
    pending = store.load_pending_outbox(request)
    sent = 0
    for row in pending:
        outbox_id = str(row.get("id") or "")
        claimed = store.try_claim_outbox_for_send(outbox_id, request)
        if not claimed:
            logger.info(
                "Outbox row already claimed: outbox_id=%s run_id=%s step_id=%s",
                outbox_id,
                request.run_id,
                request.step_id,
            )
            continue
        body_raw = claimed.get("body_json") or "{}"
        try:
            body = json.loads(body_raw)
        except json.JSONDecodeError:
            logger.warning(
                "Skipping outbox %s -- invalid body_json", claimed.get("id")
            )
            continue
        if not isinstance(body, dict):
            continue
        await bus.send(
            str(claimed.get("queue_name") or "pipeline-jobs"),
            Message(
                body=body,
                message_id=str(claimed.get("message_id") or claimed.get("id") or ""),
                correlation_id=request.run_id,
                subject=str(body.get("event_type") or "durable_step"),
            ),
        )
        sent += 1
    if not store.has_pending_outbox(request):
        store.mark_next_published(request)
    return sent
