"""Unified durable step runner for pub/sub driven pipelines.

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-36F80B95")

Replaces both the synchronous WorkflowEngine path and the hard-coded
REFERRAL_STEPS handler. Step ordering comes from relatedActions in the
Neo4j PlanDefinition; execution is one pub/sub message per step; state
is persisted in PipelineStageStore after every step.

Message format consumed by run_step():
  {
    "event_type": "durable_step",
    "action_id": "<action canvas_id>",
    "plan_definition_id": "<plan id>",
    "workflow_id": "<plan id>",
    "run_id": "...",
    "step_id": "<action canvas_id>",   (mirrors action_id for tracking)
    "patient_id": "...",
    "encounter_id": "...",
    ... (all other StepRequest fields)
  }

Activation is driven by each plan's pinned ``workflowMode`` (``durable_pubsub``)
from PlanDefinition / PlanDefinitionVersion -- not by a global feature flag.
Set ``DURABLE_ENGINE_DISABLED=true`` only for emergency rollback of new runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from libs.message_bus.base import Message, MessageBusAdapter
from libs.message_bus.settlement import MessageDeferError
from libs.neo4j_client.client import PatientGraphClient
from libs.workflow.durable_steps import StepRequest
from libs.workflow.durable_steps import StepResult as DurableStepResult
from libs.workflow.plan_manifest import (
    PlanAction as _Action,
    load_manifest_for_run,
    load_plan_manifest,
    resolve_plan_workflow_mode,
    resolve_policy_version,
)
from libs.workflow.pipeline_outbox import (
    build_first_step_message_id,
    dispatch_stage_outbox,
)
from libs.workflow.pipeline_stage_store import PipelineStageStore, StageClaimResult
from libs.workflow.run_admission import build_admission_key
from libs.workflow.stage_lease import (
    StageLeaseBusyError,
    StageLeaseStaleError,
    heartbeat_stage_lease,
    resolve_lease_owner,
)
from libs.workflow.step_contract import StepProvenance, envelope_step_result
from libs.workflow.step_state_loader import load_step_state
from libs.workflow.version_admission import (
    load_rollout_for_plan,
    select_admission_version,
)

logger = logging.getLogger(__name__)

DURABLE_STEP_EVENT = "durable_step"
_PIPELINE_QUEUE = "pipeline-jobs"

_DEFAULT_PORTS = {"else", "default", "false"}


# PlanAction (_Action) lives in plan_manifest -- pinned snapshot actions only.


# ---------------------------------------------------------------------------
# Feature flag helper
# ---------------------------------------------------------------------------


def is_durable_runner_enabled(plan_id: str) -> bool:
    """Return True when the plan declares durable_pubsub workflow activation."""
    if os.getenv("DURABLE_ENGINE_DISABLED", "false").lower() == "true":
        return False
    if not plan_id:
        return False
    return resolve_plan_workflow_mode(plan_id) == "durable_pubsub"


# ---------------------------------------------------------------------------
# Graph traversal helpers (PlanAction snapshot edges)
# ---------------------------------------------------------------------------


def _build_outgoing_edges(
    actions: list[_Action],
) -> dict[str, list[dict[str, Any]]]:
    outgoing: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    for action in actions:
        for edge in action.related_edges:
            source_id = edge.get("actionId")
            if not source_id:
                continue
            source_handle = str(edge.get("sourceHandle") or "")
            target_handle = str(edge.get("targetHandle") or "")
            dedupe_key = (source_id, action.action_id, source_handle, target_handle)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            outgoing.setdefault(source_id, []).append(
                {
                    "target": action.action_id,
                    "sourceHandle": edge.get("sourceHandle"),
                    "targetHandle": edge.get("targetHandle"),
                }
            )
        # Backward-compat fallback for plain relatedActions (no sourceHandle).
        for rel in action.related_actions:
            source_id = ""
            if isinstance(rel, str):
                source_id = rel
            elif isinstance(rel, dict):
                source_id = str(rel.get("actionId") or "")
            if not source_id:
                continue
            dedupe_key = (source_id, action.action_id, "", "")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            outgoing.setdefault(source_id, []).append(
                {"target": action.action_id, "sourceHandle": None, "targetHandle": None}
            )
    return outgoing


def _resolve_state_value(path: str, state: dict[str, Any]) -> Any:
    cursor: Any = state
    for part in path.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            return None
    return cursor


def _rule_matches(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "exists":
        return actual is not None
    if operator == "contains":
        return (
            expected is not None and actual is not None and str(expected) in str(actual)
        )
    if operator == "!=":
        return str(actual) != str(expected)
    if operator == ">":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    if operator == "<":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    return str(actual) == str(expected)


def _evaluate_condition_port(action: _Action, state: dict[str, Any]) -> str:
    params = action.config.get("params", {}) if isinstance(action.config, dict) else {}
    rules = params.get("rules") or action.config.get("rules") or []
    default_port = str(
        params.get("defaultPort") or action.config.get("defaultPort") or "else"
    )
    for rule in rules:
        field_path = str(rule.get("field") or "")
        operator = str(rule.get("operator") or "==")
        expected = rule.get("value")
        output_port = str(rule.get("outputPort") or "matched")
        actual = _resolve_state_value(field_path, state)
        if _rule_matches(actual, operator, expected):
            return output_port
    return default_port


def _resolve_next_action_ids(
    action: _Action,
    result: DurableStepResult,
    outgoing: dict[str, list[dict[str, Any]]],
) -> list[str]:
    edges = outgoing.get(action.action_id, [])
    if not edges:
        return []
    if action.node_type == "condition":
        port = (result.output or {}).get("condition_port", "else")
        matching = [e for e in edges if e.get("sourceHandle") == port]
        if not matching:
            matching = [
                e
                for e in edges
                if (e.get("sourceHandle") or "").lower() in _DEFAULT_PORTS
            ]
        return [e["target"] for e in matching]
    return [e["target"] for e in edges]


# ---------------------------------------------------------------------------
# Messaging helpers
# ---------------------------------------------------------------------------


async def _publish_durable_step(
    bus: MessageBusAdapter,
    queue_name: str,
    request: StepRequest,
    next_action_id: str,
) -> None:
    body = {
        **request.to_message(DURABLE_STEP_EVENT, next_action_id),
        "action_id": next_action_id,
    }
    await bus.send(
        queue_name,
        Message(
            body=body,
            message_id=build_first_step_message_id(request.run_id, next_action_id),
            correlation_id=request.run_id,
            subject=DURABLE_STEP_EVENT,
        ),
    )


async def _publish_completion(
    bus: MessageBusAdapter,
    request: StepRequest,
    result: DurableStepResult,
    action: _Action,
) -> None:
    if not action.completion_queue or not action.completion_event_type:
        return
    status = "completed_with_errors" if result.errors else "completed"
    body = {
        "event_type": action.completion_event_type,
        "run_id": request.run_id,
        "workflow_id": request.workflow_id,
        "plan_definition_id": request.plan_definition_id,
        "patient_id": request.patient_id,
        "encounter_id": request.encounter_id,
        "guideline_id": request.guideline_id,
        "completeness_domain": request.completeness_domain,
        "completeness_subdomain": request.completeness_subdomain,
        "status": status,
        "errors": list(result.errors),
        "context": dict(request.context),
        **(result.output or {}),
    }
    await bus.send(
        action.completion_queue,
        Message(
            body=body,
            correlation_id=request.run_id,
            subject=action.completion_event_type.replace("_", "-"),
        ),
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _with_metrics(
    result: DurableStepResult, started: float, loaded: dict[str, Any]
) -> DurableStepResult:
    metrics = dict(result.metrics)
    metrics.update(
        {
            "duration_ms": int((time.monotonic() - started) * 1000),
            "entity_count": len(
                loaded.get("entities") or result.output.get("entities") or []
            ),
        }
    )
    return DurableStepResult(
        status=result.status,
        output=result.output,
        output_refs=result.output_refs,
        warnings=result.warnings,
        errors=result.errors,
        metrics=metrics,
        provenance=dict(result.provenance),
        next_event_type=result.next_event_type,
        next_step_id=result.next_step_id,
    )


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


def _capability_provenance(action: _Action) -> StepProvenance:
    from libs.pipeline_graph.capability_registry import (
        CapabilityMetadata,
        get_capability_registry,
    )

    cap_id = action.subgraph_id or action.node_type or action.action_id
    try:
        meta = get_capability_registry().get(cap_id)
    except KeyError:
        meta = CapabilityMetadata(capability_id=cap_id)
    return StepProvenance(
        capability_id=meta.capability_id,
        capability_type=meta.capability_type,
        input_schema_version=meta.input_schema_version,
        output_schema_version=meta.output_schema_version,
        side_effect_class=meta.side_effect_class,
    )


async def _execute_action(action: _Action, state: dict[str, Any]) -> DurableStepResult:
    provenance = _capability_provenance(action)
    if action.node_type == "trigger":
        return envelope_step_result(DurableStepResult(status="completed"), provenance)
    if action.node_type == "condition":
        port = _evaluate_condition_port(action, state)
        return envelope_step_result(
            DurableStepResult(status="completed", output={"condition_port": port}),
            provenance,
        )
    from libs.pipeline_graph.registry import get_registry

    graph = get_registry().build(action.subgraph_id)
    output = await asyncio.to_thread(graph.invoke, state)
    return envelope_step_result(
        DurableStepResult(
            status="completed",
            output=dict(output or {}),
            errors=list((output or {}).get("errors") or []),
        ),
        provenance,
    )


# ---------------------------------------------------------------------------
# Progress emission
# ---------------------------------------------------------------------------


def _emit_progress(
    publisher: Any | None,
    request: StepRequest,
    event_type: str,
    action_id: str,
    result: DurableStepResult | None = None,
) -> None:
    if not publisher:
        return
    payload: dict[str, Any] = {
        "type": event_type,
        "run_id": request.run_id,
        "patient_id": request.patient_id,
        "encounter_id": request.encounter_id,
        "workflow_id": request.workflow_id,
        "action_id": action_id,
        "status": result.status if result else "running",
    }
    if result:
        payload["errors"] = result.errors
        payload["metrics"] = result.metrics
    publisher(request.run_id, payload)


# ---------------------------------------------------------------------------
# DurableStepRunner
# ---------------------------------------------------------------------------


async def _publish_successors(
    bus: MessageBusAdapter,
    queue_name: str,
    request: StepRequest,
    action: _Action,
    result: DurableStepResult,
    next_ids: list[str],
    store: PipelineStageStore,
) -> None:
    """Dispatch outbox successors or publish terminal completion."""
    if next_ids:
        await dispatch_stage_outbox(store, bus, request)
        return
    await _publish_completion(bus, request, result, action)


def _busy_defer(action_id: str, run_id: str) -> None:
    logger.info(
        "Deferring durable step -- stage lease held: action_id=%s run_id=%s",
        action_id,
        run_id,
    )
    raise StageLeaseBusyError(
        f"stage busy: {action_id} run_id={run_id}",
        action_id=action_id,
        run_id=run_id,
    )


def _successor_edges_for(
    action: _Action,
    next_action_ids: list[str],
    all_actions: list[_Action],
) -> list[dict[str, Any]]:
    outgoing = _build_outgoing_edges(all_actions)
    return [
        edge
        for edge in outgoing.get(action.action_id, [])
        if edge.get("target") in next_action_ids
    ]


async def _repair_successor_outbox(
    ctx: "_ClaimedStepContext",
    request: StepRequest,
    action: _Action,
    claim: StageClaimResult,
    all_actions: list[_Action],
) -> int:
    """Recreate missing successor outbox rows, then dispatch."""
    if not claim.next_action_ids:
        return 0
    if not ctx.store.should_repair_successor_outbox(
        request,
        claim.next_action_ids,
        next_published=claim.next_published,
    ):
        return 0
    ctx.store.ensure_successor_outbox(
        request,
        next_action_ids=claim.next_action_ids,
        successor_edges=_successor_edges_for(
            action, claim.next_action_ids, all_actions
        ),
        queue_name=ctx.queue_name,
        body_template=request.to_message(DURABLE_STEP_EVENT, request.step_id),
    )
    return await dispatch_stage_outbox(ctx.store, ctx.bus, request)


async def _requeue_sent_orphan_outbox(
    ctx: "_ClaimedStepContext",
    request: StepRequest,
    action: _Action,
    claim: StageClaimResult,
    all_actions: list[_Action],
) -> int:
    """Re-queue successors when outbox was marked sent but no stage exists."""
    if not claim.next_action_ids:
        return 0
    if not ctx.store.should_requeue_sent_orphan_outbox(
        request,
        claim.next_action_ids,
        next_published=claim.next_published,
    ):
        return 0
    logger.warning(
        "Re-queuing sent-orphan successors: action_id=%s run_id=%s next=%s",
        ctx.action_id,
        request.run_id,
        claim.next_action_ids,
    )
    ctx.store.ensure_repair_successor_outbox(
        request,
        next_action_ids=claim.next_action_ids,
        successor_edges=_successor_edges_for(
            action, claim.next_action_ids, all_actions
        ),
        queue_name=ctx.queue_name,
        body_template=request.to_message(DURABLE_STEP_EVENT, request.step_id),
    )
    return await dispatch_stage_outbox(ctx.store, ctx.bus, request)


async def _already_completed_result(
    claim: StageClaimResult,
    ctx: "_ClaimedStepContext",
    request: StepRequest,
    action: _Action,
    all_actions: list[_Action],
) -> DurableStepResult:
    logger.info(
        "Skipping durable step -- already completed: action_id=%s run_id=%s",
        ctx.action_id,
        request.run_id,
    )
    result = DurableStepResult(
        status="completed",
        output=dict(claim.output),
        warnings=["already_completed"],
        next_event_type=DURABLE_STEP_EVENT if claim.next_action_ids else None,
        next_step_id=claim.next_action_ids[0] if claim.next_action_ids else None,
    )
    if claim.next_action_ids and ctx.store.successors_need_enqueue(
        request.run_id, claim.next_action_ids
    ):
        if ctx.store.should_dispatch_successor_outbox(request, claim.next_action_ids):
            await dispatch_stage_outbox(ctx.store, ctx.bus, request)
        elif ctx.store.should_repair_successor_outbox(
            request,
            claim.next_action_ids,
            next_published=claim.next_published,
        ):
            await _repair_successor_outbox(ctx, request, action, claim, all_actions)
        elif ctx.store.should_requeue_sent_orphan_outbox(
            request,
            claim.next_action_ids,
            next_published=claim.next_published,
        ):
            await _requeue_sent_orphan_outbox(ctx, request, action, claim, all_actions)
    _emit_progress(
        ctx.publish_progress,
        request,
        "durable_step_already_completed",
        ctx.action_id,
        result,
    )
    return result


def _attach_next_event(
    result: DurableStepResult, next_ids: list[str]
) -> DurableStepResult:
    if not next_ids:
        return result
    return DurableStepResult(
        status=result.status,
        output=result.output,
        output_refs=result.output_refs,
        warnings=result.warnings,
        errors=result.errors,
        metrics=result.metrics,
        provenance=dict(result.provenance),
        next_event_type=DURABLE_STEP_EVENT,
        next_step_id=next_ids[0],
    )


@dataclass
class _ClaimedStepContext:
    body: dict[str, Any]
    action_id: str
    request: StepRequest
    client: PatientGraphClient
    store: PipelineStageStore
    bus: MessageBusAdapter
    publish_progress: Any | None
    queue_name: str
    started: float


class DurableStepRunner:
    """Execute one pipeline action per invocation, then publish the next.

    Call start() when a plan trigger event arrives. Call run_step() for
    each subsequent durable_step message.
    """

    @staticmethod
    async def start(
        body: dict[str, Any],
        *,
        bus: MessageBusAdapter,
        queue_name: str = _PIPELINE_QUEUE,
    ) -> None:
        """Handle the initial trigger: bootstrap PipelineRun, publish first action.

        Finds the action whose trigger_name matches the incoming event_type.

        - If that action is a no-op trigger node (node_type == "trigger"), it
          publishes the first downstream action instead.
        - If that action is a real subgraph action (e.g. encounter_loader), it
          publishes the action itself as the first durable_step.
        """
        request = StepRequest.from_message(body)
        trigger_event = str(body.get("event_type") or "")
        admission_key = build_admission_key(body)
        rollout = load_rollout_for_plan(request.plan_definition_id)
        policy_version, selection_reason = select_admission_version(
            body,
            rollout,
            admission_key=admission_key,
        )
        manifest = load_plan_manifest(request.plan_definition_id, policy_version)
        from libs.workflow.execution_manifest import build_manifest_for_plan

        execution_manifest = build_manifest_for_plan(manifest)
        request = StepRequest.from_message(
            {
                **body,
                "policy_version": manifest.policy_version,
                "plan_version_id": manifest.version_node_id,
                "execution_manifest": execution_manifest,
            }
        )
        client = PatientGraphClient()
        try:
            store = PipelineStageStore(client)
            store.ensure_schema()
            admission = store.admit_run(
                request,
                admission_key=admission_key,
                plan_version_id=manifest.version_node_id,
                policy_version=manifest.policy_version,
                version_selection_reason=selection_reason,
                execution_manifest_json=json.dumps(
                    execution_manifest, sort_keys=True, default=str
                ),
            )
            if admission.run_id != request.run_id:
                logger.info(
                    "DurableStepRunner.start: admission remapped "
                    "message_run_id=%s admitted_run_id=%s status=%s",
                    request.run_id,
                    admission.run_id,
                    admission.status,
                )
                request = StepRequest.from_message({**body, "run_id": admission.run_id})
            if not store.claim_first_step_enqueue(admission.run_id):
                logger.info(
                    "DurableStepRunner.start: first step already enqueued "
                    "run_id=%s message_run_id=%s status=%s",
                    admission.run_id,
                    body.get("run_id"),
                    admission.status,
                )
                return
            all_actions = list(manifest.actions)
            outgoing = _build_outgoing_edges(all_actions)
            trigger_action = next(
                (a for a in all_actions if a.trigger_name == trigger_event),
                None,
            )
            if trigger_action is None:
                logger.warning(
                    "DurableStepRunner.start: no trigger action for "
                    "event=%s plan=%s actions_loaded=%d",
                    trigger_event,
                    request.plan_definition_id,
                    len(all_actions),
                )
                store.clear_first_step_enqueue(admission.run_id)
                return
            try:
                if trigger_action.node_type == "trigger":
                    for edge in outgoing.get(trigger_action.action_id, []):
                        await _publish_durable_step(
                            bus, queue_name, request, edge["target"]
                        )
                else:
                    await _publish_durable_step(
                        bus, queue_name, request, trigger_action.action_id
                    )
            except Exception:
                store.clear_first_step_enqueue(admission.run_id)
                logger.exception(
                    "DurableStepRunner.start: first-step publish failed; "
                    "cleared enqueue claim run_id=%s",
                    admission.run_id,
                )
                raise
        finally:
            client.close()

    @staticmethod
    async def run_step(
        body: dict[str, Any],
        *,
        bus: MessageBusAdapter,
        publish_progress: Any | None = None,
        queue_name: str = _PIPELINE_QUEUE,
    ) -> DurableStepResult:
        """Execute one action from a durable_step message.

        Claims the PipelineStageRun before work so Service Bus redelivery
        cannot run the same stage twice. Already-completed stages skip the
        subgraph and only repair unpublished next-step messages.
        """
        action_id = str(body.get("action_id") or "")
        request = StepRequest.from_message(body)
        if not request.step_id:
            request = StepRequest.from_message({**body, "step_id": action_id})
        started = time.monotonic()
        client = PatientGraphClient()
        store = PipelineStageStore(client)
        ctx = _ClaimedStepContext(
            body=body,
            action_id=action_id,
            request=request,
            client=client,
            store=store,
            bus=bus,
            publish_progress=publish_progress,
            queue_name=queue_name,
            started=started,
        )
        try:
            return await DurableStepRunner._run_claimed_step(ctx)
        except MessageDeferError:
            # Expected when another delivery holds the stage lease or completion
            # must be retried; the pipeline worker abandons the Service Bus msg.
            raise
        except Exception as exc:
            logger.exception(
                "DurableStepRunner step failed: action_id=%s run_id=%s",
                action_id,
                request.run_id,
            )
            failed = DurableStepResult(status="failed", errors=[str(exc)])
            try:
                store.complete_stage(request, failed)
            except Exception:
                logger.debug("Failed to persist step failure", exc_info=True)
            _emit_progress(
                publish_progress, request, "durable_step_failed", action_id, failed
            )
            raise
        finally:
            client.close()

    @staticmethod
    async def _run_claimed_step(ctx: _ClaimedStepContext) -> DurableStepResult:
        # LONG FUNCTION: claim, load, execute, complete, and publish successors.
        store = ctx.store
        request = ctx.request
        action_id = ctx.action_id
        store.ensure_schema()
        store.upsert_run(request, status="running")
        manifest = load_manifest_for_run(
            request.run_id,
            request.plan_definition_id,
            resolve_policy_version(ctx.body),
            client=ctx.client,
        )
        all_actions = list(manifest.actions)
        action = {a.action_id: a for a in all_actions}.get(action_id)
        if action is None:
            raise ValueError(
                f"Action '{action_id}' not found in plan "
                f"'{request.plan_definition_id}'"
            )
        stage_label = action.subgraph_id or action.node_type or action_id
        if request.event_type == DURABLE_STEP_EVENT:
            request = StepRequest.from_message(
                {
                    **ctx.body,
                    "step_id": request.step_id or action_id,
                    "event_type": stage_label,
                }
            )
        loaded = load_step_state(ctx.client, store, request, body=ctx.body)
        lease_owner = resolve_lease_owner(ctx.body)
        claim = store.claim_stage(request, loaded, lease_owner=lease_owner)
        if claim.outcome == "busy":
            _busy_defer(action_id, request.run_id)
        if claim.outcome == "poisoned":
            poisoned = DurableStepResult(
                status="poisoned",
                errors=["stage_poisoned_max_attempts"],
            )
            _emit_progress(
                ctx.publish_progress,
                request,
                "durable_step_poisoned",
                action_id,
                poisoned,
            )
            return poisoned
        if claim.outcome == "already_completed":
            return await _already_completed_result(
                claim, ctx, request, action, all_actions
            )
        _emit_progress(ctx.publish_progress, request, "durable_step_started", action_id)
        heartbeat = asyncio.create_task(
            heartbeat_stage_lease(
                store,
                request,
                lease_owner=claim.lease_owner,
                lease_generation=claim.lease_generation,
                lease_seconds=max(
                    60, int(os.getenv("PIPELINE_STAGE_LEASE_SECONDS", "3600"))
                ),
            )
        )
        try:
            result = await _execute_action(action, loaded)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
        result = _with_metrics(result, ctx.started, loaded)
        outgoing = _build_outgoing_edges(all_actions)
        next_ids = _resolve_next_action_ids(action, result, outgoing)
        result = _attach_next_event(result, next_ids)
        successor_edges = [
            edge
            for edge in outgoing.get(action.action_id, [])
            if edge.get("target") in next_ids
        ]
        complete = store.complete_stage(
            request,
            result,
            next_action_ids=next_ids,
            successor_edges=successor_edges,
            queue_name=ctx.queue_name,
            body_template=request.to_message(
                DURABLE_STEP_EVENT, request.step_id or action_id
            ),
            next_published=False,
            lease_owner=claim.lease_owner,
            lease_generation=claim.lease_generation,
        )
        if complete.outcome == "stale_lease":
            replay = store.claim_stage(request, loaded, lease_owner=lease_owner)
            if replay.outcome == "already_completed":
                logger.info(
                    "Stale lease on complete -- stage already finished: "
                    "action_id=%s run_id=%s owner=%s gen=%s",
                    action_id,
                    request.run_id,
                    claim.lease_owner,
                    claim.lease_generation,
                )
                return await _already_completed_result(
                    replay, ctx, request, action, all_actions
                )
            logger.warning(
                "Stale lease on complete: action_id=%s run_id=%s owner=%s gen=%s",
                action_id,
                request.run_id,
                claim.lease_owner,
                claim.lease_generation,
            )
            raise StageLeaseStaleError(
                f"stale lease on complete: action_id={action_id} "
                f"run_id={request.run_id}",
                action_id=action_id,
                run_id=request.run_id,
                lease_owner=claim.lease_owner,
                lease_generation=claim.lease_generation,
            )
        _emit_progress(
            ctx.publish_progress, request, "durable_step_completed", action_id, result
        )
        await _publish_successors(
            ctx.bus, ctx.queue_name, request, action, result, next_ids, store
        )
        return result
