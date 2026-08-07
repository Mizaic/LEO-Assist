"""Recover PipelineRun rows stuck after sent-orphan or lost first-step.

Atlas trace:
  DI: DI-4976171D
  DO: DO-3A657CCF
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-4976171D")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from libs.message_bus.base import MessageBusAdapter
from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    _build_outgoing_edges,
    _publish_durable_step,
)
from libs.workflow.durable_steps import StepRequest
from libs.workflow.plan_manifest import load_manifest_for_run, load_plan_manifest
from libs.workflow.pipeline_outbox import (
    build_first_step_message_id,
    build_first_step_recovery_message_id,
    dispatch_stage_outbox,
)
from libs.workflow.pipeline_stage_store import PipelineStageStore

logger = logging.getLogger(__name__)

_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")


def _parse_next_ids(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _request_from_stuck_row(run_id: str, row: dict[str, Any]) -> StepRequest:
    case_id = str(row.get("case_id") or "")
    return StepRequest(
        event_type=DURABLE_STEP_EVENT,
        run_id=run_id,
        workflow_id=str(row.get("plan_definition_id") or ""),
        plan_definition_id=str(row.get("plan_definition_id") or ""),
        step_id=str(row.get("step_id") or ""),
        patient_id=str(row.get("patient_id") or ""),
        encounter_id=str(row.get("encounter_id") or ""),
        context={"case_id": case_id} if case_id else {},
    )


def _load_manifest(client: Any, run_id: str, plan_id: str) -> Any:
    try:
        return load_manifest_for_run(run_id, plan_id, "latest", client=client)
    except Exception:
        logger.debug(
            "Manifest load failed for stuck recovery run_id=%s", run_id, exc_info=True
        )
        return load_plan_manifest(plan_id)


def _successor_edges(
    manifest: Any,
    step_id: str,
    next_ids: list[str],
) -> list[dict[str, Any]]:
    if manifest is None:
        return []
    outgoing = _build_outgoing_edges(list(manifest.actions))
    return [
        edge for edge in outgoing.get(step_id, []) if edge.get("target") in next_ids
    ]


async def _dispatch_pending_or_repair(
    store: PipelineStageStore,
    bus: MessageBusAdapter,
    request: StepRequest,
    next_ids: list[str],
    *,
    next_published: bool,
    edges: list[dict[str, Any]],
    queue_name: str,
) -> int:
    if store.should_dispatch_successor_outbox(request, next_ids):
        return await dispatch_stage_outbox(store, bus, request)
    if store.should_repair_successor_outbox(
        request, next_ids, next_published=next_published
    ):
        store.ensure_successor_outbox(
            request,
            next_action_ids=next_ids,
            successor_edges=edges,
            queue_name=queue_name,
        )
        return await dispatch_stage_outbox(store, bus, request)
    if not store.should_requeue_sent_orphan_outbox(
        request, next_ids, next_published=next_published
    ):
        return 0
    logger.warning(
        "Stuck-run recovery re-queuing successors: run_id=%s step=%s next=%s",
        request.run_id,
        request.step_id,
        next_ids,
    )
    store.ensure_repair_successor_outbox(
        request,
        next_action_ids=next_ids,
        successor_edges=edges,
        queue_name=queue_name,
    )
    return await dispatch_stage_outbox(store, bus, request)


async def _recover_sent_orphan(
    client: Any,
    store: PipelineStageStore,
    bus: MessageBusAdapter,
    run_id: str,
    row: dict[str, Any],
    *,
    queue_name: str,
) -> int:
    next_ids = _parse_next_ids(row.get("next_action_ids_json"))
    if not next_ids:
        return 0
    request = _request_from_stuck_row(run_id, row)
    plan_id = str(row.get("plan_definition_id") or "")
    manifest = _load_manifest(client, run_id, plan_id)
    edges = _successor_edges(manifest, request.step_id, next_ids)
    return await _dispatch_pending_or_repair(
        store,
        bus,
        request,
        next_ids,
        next_published=bool(row.get("next_published")),
        edges=edges,
        queue_name=queue_name,
    )


async def _recover_zero_stage(
    client: Any,
    store: PipelineStageStore,
    bus: MessageBusAdapter,
    run_id: str,
    row: dict[str, Any],
    *,
    queue_name: str,
) -> int:
    plan_id = str(row.get("plan_definition_id") or "")
    manifest = _load_manifest(client, run_id, plan_id)
    if manifest is None:
        return 0
    case_id = str(row.get("case_id") or "")
    request = StepRequest(
        event_type=DURABLE_STEP_EVENT,
        run_id=run_id,
        workflow_id=plan_id,
        plan_definition_id=plan_id,
        step_id="",
        patient_id=str(row.get("patient_id") or ""),
        encounter_id=str(row.get("encounter_id") or ""),
        context={"case_id": case_id} if case_id else {},
    )
    trigger = next((a for a in manifest.actions if a.trigger_name), None)
    if trigger is None:
        return 0
    recovery_generation = 0
    if bool(row.get("first_step_enqueued")):
        bumped = store.reset_first_step_for_recovery(run_id)
        if bumped is None:
            return 0
        recovery_generation = bumped
    elif not store.claim_first_step_enqueue(run_id):
        return 0
    outgoing = _build_outgoing_edges(list(manifest.actions))
    if trigger.node_type == "trigger":
        raw_targets = [e["target"] for e in outgoing.get(trigger.action_id, [])]
    else:
        raw_targets = [trigger.action_id]
    targets = list(dict.fromkeys(raw_targets))
    try:
        for target in targets:
            message_id = (
                build_first_step_recovery_message_id(
                    run_id, target, recovery_generation
                )
                if recovery_generation > 0
                else build_first_step_message_id(run_id, target)
            )
            await _publish_durable_step(
                bus,
                queue_name,
                request,
                target,
                message_id=message_id,
            )
        logger.warning(
            "Stuck-run recovery republished first step: run_id=%s targets=%s "
            "recovery_generation=%s",
            run_id,
            targets,
            recovery_generation,
        )
        return len(targets)
    except Exception:
        store.clear_first_step_enqueue(run_id)
        logger.exception(
            "Stuck-run recovery first-step publish failed: run_id=%s", run_id
        )
        return 0


async def recover_stuck_pipeline_run(
    client: Any,
    bus: MessageBusAdapter,
    run_id: str,
    *,
    queue_name: str | None = None,
) -> int:
    """Best-effort recovery for a running PipelineRun with no active work."""
    queue = queue_name or _PIPELINE_QUEUE
    store = PipelineStageStore(client)
    if store.get_run_status(run_id) != "running":
        return 0
    stuck = store.load_stuck_completed_stage(run_id)
    if stuck:
        return await _recover_sent_orphan(
            client, store, bus, run_id, stuck, queue_name=queue
        )
    zero = store.load_zero_stage_running_run(run_id)
    if zero:
        return await _recover_zero_stage(
            client, store, bus, run_id, zero, queue_name=queue
        )
    return 0


def recover_stuck_pipeline_run_sync(client: Any, run_id: str) -> int:
    """Sync wrapper used by Lab refresh_run (creates a short-lived bus)."""
    from libs.message_bus.factory import create_message_bus
    from libs.validation_lab.pipeline import _run_coro_sync

    async def _run() -> int:
        bus = create_message_bus()
        try:
            return await recover_stuck_pipeline_run(client, bus, run_id)
        finally:
            try:
                await bus.close()
            except BaseException:
                logger.debug("bus close after stuck recovery failed", exc_info=True)

    try:
        return int(_run_coro_sync(_run) or 0)
    except Exception:
        logger.exception("Stuck pipeline recovery failed: run_id=%s", run_id)
        return 0
