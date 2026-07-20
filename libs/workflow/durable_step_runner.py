"""Unified durable step runner for pub/sub driven pipelines.

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

Controlled by the DURABLE_ENGINE_ENABLED environment variable:
  false     -- disabled (default, legacy paths still active)
  referral  -- enable for pd-referral-assessment only
  true/all  -- enable for all durable_pubsub plans
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from libs.message_bus.base import Message, MessageBusAdapter
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.workflow.durable_steps import StepRequest
from libs.workflow.durable_steps import StepResult as DurableStepResult
from libs.workflow.pipeline_stage_store import PipelineStageStore
from libs.workflow.step_state_loader import load_step_state

logger = logging.getLogger(__name__)

DURABLE_STEP_EVENT = "durable_step"
_PIPELINE_QUEUE = "pipeline-jobs"

_SUBGRAPH_IMPLIES_NODE_TYPE = {"condition": "condition", "trigger": "trigger"}
_DEFAULT_PORTS = {"else", "default", "false"}


# ---------------------------------------------------------------------------
# ActionDefinition (local, sync-friendly copy of the engine dataclass)
# ---------------------------------------------------------------------------


@dataclass
class _Action:
    action_id: str
    subgraph_id: str
    node_type: str = "action"
    config: dict[str, Any] = field(default_factory=dict)
    related_actions: list[Any] = field(default_factory=list)
    related_edges: list[dict[str, Any]] = field(default_factory=list)
    sequence: int = 0
    trigger_name: str = ""
    completion_queue: str = ""
    completion_event_type: str = ""


# ---------------------------------------------------------------------------
# Feature flag helper
# ---------------------------------------------------------------------------


def _enabled_flag() -> str:
    return os.getenv("DURABLE_ENGINE_ENABLED", "false").lower()


def is_durable_runner_enabled(plan_id: str) -> bool:
    """Return True when DurableStepRunner should handle this plan."""
    flag = _enabled_flag()
    if flag == "false":
        return False
    if flag == "referral":
        return plan_id == "pd-referral-assessment"
    return True


# ---------------------------------------------------------------------------
# Neo4j action loading (PlanDefinition lives on the Knowledge Graph)
# ---------------------------------------------------------------------------

_LOAD_ACTIONS_QUERY = """
MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_ACTION]->(a:Action)
OPTIONAL MATCH (a)-[:USES_DEFINITION]->(ad:ActivityDefinition)
RETURN a, ad
ORDER BY a.sequence
"""

_LOAD_PLAN_QUERY = """
MATCH (pd:PlanDefinition {id: $plan_id})
RETURN pd.workflowMode AS workflow_mode
LIMIT 1
"""


def _record_to_action(row: dict[str, Any]) -> _Action:
    action_node = row["a"]
    ad_node = row.get("ad")
    config: dict[str, Any] = {}
    if ad_node and ad_node.get("dynamicValues"):
        try:
            config = json.loads(ad_node["dynamicValues"])
        except (json.JSONDecodeError, TypeError):
            pass
    related_edges_raw = action_node.get("relatedActionEdges")
    related_edges: list[dict[str, Any]] = []
    if related_edges_raw:
        try:
            related_edges = json.loads(related_edges_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    action_id = action_node.get("canvas_id") or action_node["id"]
    resolved_subgraph_id = (
        ad_node["subgraphId"] if ad_node else action_node.get("subgraphId", "")
    )
    implied_node_type = _SUBGRAPH_IMPLIES_NODE_TYPE.get(resolved_subgraph_id)
    raw_node_type = action_node.get("nodeType") or action_node.get("node_type", "")
    if implied_node_type is not None:
        node_type = implied_node_type
    else:
        node_type = raw_node_type or "action"
    return _Action(
        action_id=action_id,
        subgraph_id=resolved_subgraph_id,
        node_type=node_type,
        config=config,
        related_actions=action_node.get("relatedActions") or [],
        related_edges=related_edges,
        sequence=int(action_node.get("sequence", 0)),
        trigger_name=action_node.get("trigger_name", ""),
        completion_queue=action_node.get("completionQueue", ""),
        completion_event_type=action_node.get("completionEventType", ""),
    )


def _load_all_actions(plan_id: str) -> list[_Action]:
    """Load PlanDefinition actions from the Knowledge Graph.

    PlanDefinitions / Actions are KG resources (same as WorkflowEngine).
    PipelineRun / PipelineStage state stays on the Patient Graph.
    """
    client = KnowledgeGraphClient()
    try:
        rows = client.run(_LOAD_ACTIONS_QUERY, plan_id=plan_id)
        return [_record_to_action(r) for r in (rows or [])]
    finally:
        client.close()


def _get_plan_workflow_mode(plan_id: str) -> str:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(_LOAD_PLAN_QUERY, plan_id=plan_id)
        if rows:
            return str(rows[0].get("workflow_mode") or "")
        return ""
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Graph traversal helpers (copied from engine.py, adapted for _Action)
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
        next_event_type=result.next_event_type,
        next_step_id=result.next_step_id,
    )


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


async def _execute_action(action: _Action, state: dict[str, Any]) -> DurableStepResult:
    if action.node_type == "trigger":
        return DurableStepResult(status="completed")
    if action.node_type == "condition":
        port = _evaluate_condition_port(action, state)
        return DurableStepResult(status="completed", output={"condition_port": port})
    from libs.pipeline_graph.registry import get_registry

    graph = get_registry().build(action.subgraph_id)
    output = await asyncio.to_thread(graph.invoke, state)
    return DurableStepResult(
        status="completed",
        output=dict(output or {}),
        errors=list((output or {}).get("errors") or []),
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
        client = PatientGraphClient()
        try:
            store = PipelineStageStore(client)
            store.ensure_schema()
            store.upsert_run(request, status="running")
            all_actions = _load_all_actions(request.plan_definition_id)
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
                return
            if trigger_action.node_type == "trigger":
                # No-op trigger: enqueue the first real downstream action.
                for edge in outgoing.get(trigger_action.action_id, []):
                    await _publish_durable_step(
                        bus, queue_name, request, edge["target"]
                    )
            else:
                # Real action that also carries the trigger annotation;
                # publish it directly as the first step.
                await _publish_durable_step(
                    bus, queue_name, request, trigger_action.action_id
                )
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

        Loads state, runs the subgraph, persists output, then publishes the
        next action(s). Terminal steps trigger a completion message on the
        configured completion queue.
        """
        action_id = str(body.get("action_id") or "")
        request = StepRequest.from_message(body)
        if not request.step_id:
            request = StepRequest.from_message({**body, "step_id": action_id})
        started = time.monotonic()
        client = PatientGraphClient()
        try:
            store = PipelineStageStore(client)
            store.ensure_schema()
            store.upsert_run(request, status="running")
            all_actions = _load_all_actions(request.plan_definition_id)
            action_map = {a.action_id: a for a in all_actions}
            action = action_map.get(action_id)
            if action is None:
                raise ValueError(
                    f"Action '{action_id}' not found in plan "
                    f"'{request.plan_definition_id}'"
                )
            # Persist a readable stage label (subgraph id) instead of the
            # generic durable_step event_type used on the bus message.
            stage_label = action.subgraph_id or action.node_type or action_id
            if request.event_type == DURABLE_STEP_EVENT:
                request = StepRequest.from_message(
                    {
                        **body,
                        "step_id": request.step_id or action_id,
                        "event_type": stage_label,
                    }
                )
            loaded = load_step_state(client, store, request, body=body)
            store.start_stage(request, loaded)
            _emit_progress(publish_progress, request, "durable_step_started", action_id)
            result = await _execute_action(action, loaded)
            result = _with_metrics(result, started, loaded)
            # Resolve successors before complete_stage so PipelineRun stays
            # "running" while more durable_step messages are in flight.
            # PipelineStageStore.complete_stage treats missing next_event_type
            # as terminal "completed", which stopped the scenario-runs UI
            # auto-refresh mid-pipeline.
            outgoing = _build_outgoing_edges(all_actions)
            next_ids = _resolve_next_action_ids(action, result, outgoing)
            if next_ids:
                result = DurableStepResult(
                    status=result.status,
                    output=result.output,
                    output_refs=result.output_refs,
                    warnings=result.warnings,
                    errors=result.errors,
                    metrics=result.metrics,
                    next_event_type=DURABLE_STEP_EVENT,
                    next_step_id=next_ids[0],
                )
            store.complete_stage(request, result)
            _emit_progress(
                publish_progress, request, "durable_step_completed", action_id, result
            )
            if next_ids:
                for next_id in next_ids:
                    await _publish_durable_step(bus, queue_name, request, next_id)
            else:
                await _publish_completion(bus, request, result, action)
            return result
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
