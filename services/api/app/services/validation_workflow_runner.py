"""Execute UN-scoped validation PlanDefinitions.

Atlas trace:
  UN: UN-89E2AE36, UN-5F3BF083, UN-AF530E8E, UN-CBF42476, UN-F8819A42
  VAL: VAL-87173594
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from libs.workflow.engine import ActionDefinition, WorkflowEngine
from libs.workflow.validation_workflows import (
    VALIDATION_WORKFLOW_SPECS,
    all_validation_plan_definitions,
    get_validation_spec,
)

logger = logging.getLogger(__name__)


def _activity_config(activity_id: str) -> dict[str, Any]:
    from scripts.seed_plan_definitions import ACTIVITY_DEFINITIONS

    for activity in ACTIVITY_DEFINITIONS:
        if activity.get("id") != activity_id:
            continue
        config = {"label": activity.get("name", activity_id)}
        for dynamic_value in activity.get("dynamicValue", []):
            path = dynamic_value.get("path")
            expression = dynamic_value.get("expression", {}).get("expression")
            if path:
                config[path] = expression
        return config
    return {"label": activity_id}


def _plan_by_id(plan_definition_id: str) -> dict[str, Any]:
    for plan in all_validation_plan_definitions():
        if plan.get("id") == plan_definition_id:
            return plan
    raise KeyError(f"Unknown validation PlanDefinition: {plan_definition_id}")


def _actions_from_plan(plan: dict[str, Any]) -> list[ActionDefinition]:
    actions: list[ActionDefinition] = []
    for raw_action in plan.get("action", []):
        definition = raw_action.get("definitionCanonical", "")
        activity_id = definition.split("/")[-1] if definition else ""
        trigger = (raw_action.get("trigger") or [{}])[0]
        config = _activity_config(activity_id)
        config["label"] = raw_action.get("title", config.get("label", activity_id))
        actions.append(
            ActionDefinition(
                action_id=raw_action["id"],
                subgraph_id=raw_action.get("_subgraphId", ""),
                trigger_type=trigger.get("type", ""),
                trigger_name=trigger.get("name", ""),
                node_type=raw_action.get("_nodeType", "action"),
                condition=raw_action.get("condition"),
                config=config,
                related_actions=raw_action.get("relatedAction", []),
                related_edges=raw_action.get("relatedActionEdges", []),
                sequence=int(raw_action.get("_sequence", 0)),
            )
        )
    return actions


async def _run_actions(
    engine: WorkflowEngine,
    actions: list[ActionDefinition],
    initial_state: dict[str, Any],
) -> dict[str, Any]:
    from libs.workflow.model_defaults import apply_single_model_defaults

    pipeline_state = dict(initial_state)
    pipeline_state.setdefault("dry_run", True)
    pipeline_state.setdefault("errors", [])
    pipeline_state.setdefault("capture_validation_output", True)
    apply_single_model_defaults(pipeline_state)
    steps: list[dict[str, Any]] = []

    for action in sorted(actions, key=lambda item: item.sequence):
        step_state = engine._build_step_state(action, pipeline_state)
        result = await engine._execute_step(action, step_state)
        if result.status == "error":
            return {
                "status": "error",
                "steps": steps,
                "final_state": pipeline_state,
                "error": result.error,
            }
        output = engine._apply_field_mappings_to_output(
            action,
            pipeline_state,
            result.output,
        )
        result.output = output
        engine._merge_step_output(pipeline_state, output)
        persist_error = engine._persist_failure(action, output)
        steps.append(
            {
                "action_id": action.action_id,
                "subgraph_id": action.subgraph_id,
                "status": "error" if persist_error else result.status,
                "error": persist_error or result.error,
                "entity_count": result.entity_count,
            }
        )
        if persist_error:
            return {
                "status": "error",
                "steps": steps,
                "final_state": pipeline_state,
                "error": persist_error,
            }

    return {"status": "completed", "steps": steps, "final_state": pipeline_state}


async def execute_validation_workflow(
    *,
    un_id: str,
    initial_state: dict[str, Any],
    engine: WorkflowEngine | None = None,
) -> dict[str, Any]:
    spec = get_validation_spec(un_id)
    plan = _plan_by_id(spec.plan_definition_id)
    actions = _actions_from_plan(plan)
    run_state = {
        "un_id": spec.un_id,
        "val_id": spec.val_id,
        "plan_definition_id": spec.plan_definition_id,
        **initial_state,
    }
    result = await _run_actions(engine or WorkflowEngine(), actions, run_state)
    result["un_id"] = spec.un_id
    result["val_id"] = spec.val_id
    result["plan_definition_id"] = spec.plan_definition_id
    return result


def execute_validation_workflow_sync(
    *,
    un_id: str,
    initial_state: dict[str, Any],
    engine: WorkflowEngine | None = None,
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            execute_validation_workflow(
                un_id=un_id,
                initial_state=initial_state,
                engine=engine,
            )
        )
    raise RuntimeError("execute_validation_workflow_sync cannot run in an event loop")


def validation_workflow_catalog() -> list[dict[str, Any]]:
    return [
        {
            "un_id": spec.un_id,
            "val_id": spec.val_id,
            "plan_definition_id": spec.plan_definition_id,
            "metric": spec.metric,
            "output_contract": list(spec.output_contract),
        }
        for spec in VALIDATION_WORKFLOW_SPECS.values()
    ]
