"""WorkflowEngine: interprets FHIR PlanDefinitions stored in Neo4j,
matches incoming events to actions, resolves ActivityDefinitions to
subgraph configurations, and dispatches execution via SubgraphRegistry.

State chaining: each step's output is merged into a shared pipeline state
that feeds the next step.  Entity key normalisation maps subgraph-specific
keys (processed_entities, resolved_entities) back to the canonical
``entities`` key so downstream steps always find them.

Verification gate: if the verification subgraph sets ``is_verified=False``
the pipeline halts and the run is marked ``needs_review``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from libs.pipeline_graph.registry import get_registry

logger = logging.getLogger(__name__)

_ENTITY_KEY_ALIASES = {"processed_entities", "resolved_entities"}

HALT_SUBGRAPHS = frozenset()


@dataclass
class WorkflowEvent:
    event_type: str
    patient_id: str
    encounter_id: str | None = None
    plan_definition_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ActionDefinition:
    action_id: str
    subgraph_id: str
    trigger_type: str
    trigger_name: str
    condition: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    related_actions: list[str] = field(default_factory=list)
    sequence: int = 0


@dataclass
class StepResult:
    action_id: str
    subgraph_id: str
    status: str
    duration_ms: int = 0
    entity_count: int = 0
    is_verified: bool | None = None
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """Interprets FHIR PlanDefinitions and dispatches LangGraph subgraphs.

    Pipeline execution resolves the full ordered action chain from
    trigger action through all sequenced actions, passing state from
    each step to the next.
    """

    def __init__(self, neo4j_driver=None, message_bus=None):
        self._driver = neo4j_driver
        self._bus = message_bus
        self._registry = get_registry()

    async def handle_event(self, event: WorkflowEvent) -> dict[str, Any]:
        """Execute the full pipeline chain for an event."""
        chain = await self._resolve_action_chain(event)
        if not chain:
            logger.warning("No actions matched event %s for plan %s",
                           event.event_type, event.plan_definition_id)
            return {"status": "no_match", "steps": []}

        pipeline_state: dict[str, Any] = {
            "patient_id": event.patient_id,
            "encounter_id": event.encounter_id or "",
            "run_id": event.run_id,
            "errors": [],
        }
        pipeline_state.update(event.context)

        step_results: list[StepResult] = []
        final_status = "completed"

        for action in chain:
            step_state = self._build_step_state(action, pipeline_state)

            step_result = await self._execute_step(action, step_state)
            step_results.append(step_result)

            if step_result.status == "error":
                final_status = "error"
                logger.error("Pipeline halted at %s: %s",
                             action.action_id, step_result.error)
                break

            self._merge_step_output(pipeline_state, step_result.output)

            entities = pipeline_state.get("entities") or []
            if action.subgraph_id == "extraction" and not entities:
                final_status = "empty_extraction"
                logger.warning("Extraction returned 0 entities — aborting pipeline")
                break

            if action.subgraph_id == "verification":
                is_verified = pipeline_state.get("is_verified", True)
                if not is_verified:
                    final_status = "needs_review"
                    logger.info("Verification failed — pipeline halted for review")
                    break

        await self._write_audit_event(event, step_results, final_status, pipeline_state)

        return {
            "status": final_status,
            "run_id": event.run_id,
            "steps": [
                {
                    "action_id": sr.action_id,
                    "subgraph_id": sr.subgraph_id,
                    "status": sr.status,
                    "duration_ms": sr.duration_ms,
                    "entity_count": sr.entity_count,
                    "is_verified": sr.is_verified,
                    "error": sr.error,
                }
                for sr in step_results
            ],
            "entity_count": len(pipeline_state.get("entities") or []),
        }

    async def evaluate_plan(self, event: WorkflowEvent) -> list[ActionDefinition]:
        """Find actions in the PlanDefinition whose triggers match this event."""
        if not event.plan_definition_id:
            return await self._find_matching_plans(event)
        return await self._get_triggered_actions(event.plan_definition_id, event.event_type)

    async def _execute_step(
        self, action: ActionDefinition, state: dict[str, Any],
    ) -> StepResult:
        """Run a single subgraph step and capture timing."""
        logger.info(
            "Executing step %s (subgraph=%s) for patient %s",
            action.action_id, action.subgraph_id, state.get("patient_id"),
        )
        t0 = time.monotonic()
        try:
            subgraph = self._registry.build(action.subgraph_id)
            result = subgraph.invoke(state)
            duration = int((time.monotonic() - t0) * 1000)
            entities = (
                result.get("entities")
                or result.get("processed_entities")
                or result.get("resolved_entities")
                or []
            )
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="completed",
                duration_ms=duration,
                entity_count=len(entities),
                is_verified=result.get("is_verified"),
                output=result,
            )
        except KeyError:
            duration = int((time.monotonic() - t0) * 1000)
            logger.error("Subgraph %s not registered", action.subgraph_id)
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="error",
                duration_ms=duration,
                error=f"Unknown subgraph: {action.subgraph_id}",
            )
        except Exception as exc:
            duration = int((time.monotonic() - t0) * 1000)
            logger.error("Step %s failed: %s", action.action_id, exc, exc_info=True)
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="error",
                duration_ms=duration,
                error=str(exc),
            )

    def _build_step_state(
        self, action: ActionDefinition, pipeline_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the input state for a single step by merging pipeline state with action config."""
        state = dict(pipeline_state)
        state.update(action.config)

        prompt_config_id = state.get("prompt_config_id")
        if prompt_config_id and "prompt_config" not in state:
            state["prompt_config"] = self._load_prompt_config(prompt_config_id)

        return state

    @staticmethod
    def _merge_step_output(
        pipeline_state: dict[str, Any], step_output: dict[str, Any],
    ) -> None:
        """Merge a subgraph's output into the shared pipeline state.

        Normalises entity keys so all downstream steps find entities
        under the canonical ``entities`` key.
        """
        for key, value in step_output.items():
            if key in _ENTITY_KEY_ALIASES and value:
                pipeline_state["entities"] = value
            elif key == "errors" and value:
                existing = pipeline_state.get("errors") or []
                pipeline_state["errors"] = existing + list(value)
            else:
                pipeline_state[key] = value

    async def _resolve_action_chain(
        self, event: WorkflowEvent,
    ) -> list[ActionDefinition]:
        """Resolve the full ordered sequence of actions starting from trigger.

        Loads ALL actions for the PlanDefinition, finds the trigger action(s),
        then walks the relatedAction graph (using sequence order) to build
        the complete chain.
        """
        if not self._driver or not event.plan_definition_id:
            return await self.evaluate_plan(event)

        all_actions = await self._get_all_plan_actions(event.plan_definition_id)
        if not all_actions:
            return []

        trigger_actions = [
            a for a in all_actions
            if a.trigger_name == event.event_type
        ]
        if not trigger_actions:
            return []

        action_by_id = {a.action_id: a for a in all_actions}
        visited: set[str] = set()
        chain: list[ActionDefinition] = []

        queue = list(trigger_actions)
        while queue:
            action = queue.pop(0)
            if action.action_id in visited:
                continue
            visited.add(action.action_id)
            chain.append(action)

        remaining = [
            a for a in all_actions
            if a.action_id not in visited
        ]
        remaining.sort(key=lambda a: a.sequence)
        chain.extend(remaining)

        return chain

    async def schedule_timer(
        self, plan_definition_id: str, action_id: str,
        patient_id: str, delay_seconds: int,
    ) -> None:
        """Schedule a future event via Service Bus scheduled messages."""
        if not self._bus:
            logger.warning("No message bus configured — cannot schedule timer")
            return
        message = {
            "event_type": "timer",
            "patient_id": patient_id,
            "plan_definition_id": plan_definition_id,
            "context": {"timer_action_id": action_id},
        }
        logger.info("Scheduling timer for action %s in %ds", action_id, delay_seconds)
        await self._bus.send("pipeline-jobs", message, schedule_after_seconds=delay_seconds)

    def _load_prompt_config(self, config_id: str) -> dict[str, Any]:
        """Load a PromptConfig from Neo4j by ID, returning a dict for subgraph state."""
        try:
            from libs.cypher.prompt_config_queries import GET_PROMPT
            from app.db.neo4j_client import PatientGraphClient

            client = PatientGraphClient()
            try:
                with client.session() as session:
                    row = session.run(GET_PROMPT, id=config_id).single()
                if row:
                    few_shot_raw = row.get("fewShotExamples") or "[]"
                    try:
                        few_shot = json.loads(few_shot_raw) if isinstance(few_shot_raw, str) else few_shot_raw
                    except (ValueError, TypeError):
                        few_shot = []
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "version": row.get("version", 1),
                        "systemPrompt": row["systemPrompt"],
                        "outputSchema": row.get("outputSchema") or "{}",
                        "fewShotExamples": few_shot,
                    }
            finally:
                client.close()
        except Exception as exc:
            logger.warning("Failed to load PromptConfig %s: %s", config_id, exc)
        return {}

    async def _get_all_plan_actions(self, plan_id: str) -> list[ActionDefinition]:
        """Load every action for a PlanDefinition, ordered by sequence."""
        if not self._driver:
            return []
        query = """
        MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_ACTION]->(a:Action)
        OPTIONAL MATCH (a)-[:USES_DEFINITION]->(ad:ActivityDefinition)
        RETURN a, ad
        ORDER BY a.sequence
        """
        actions = []
        async with self._driver.session() as session:
            result = await session.run(query, plan_id=plan_id)
            async for record in result:
                actions.append(self._record_to_action(record))
        return actions

    async def _get_triggered_actions(self, plan_id: str, event_type: str) -> list[ActionDefinition]:
        """Query Neo4j for actions matching the event type."""
        if not self._driver:
            logger.warning("No Neo4j driver — returning empty actions")
            return []
        query = """
        MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_ACTION]->(a:Action)
        WHERE a.trigger_type = 'data-changed' AND a.trigger_name = $event_type
        OPTIONAL MATCH (a)-[:USES_DEFINITION]->(ad:ActivityDefinition)
        RETURN a, ad
        ORDER BY a.sequence
        """
        actions = []
        async with self._driver.session() as session:
            result = await session.run(query, plan_id=plan_id, event_type=event_type)
            async for record in result:
                actions.append(self._record_to_action(record))
        return actions

    async def _find_matching_plans(self, event: WorkflowEvent) -> list[ActionDefinition]:
        """Find all PlanDefinitions with actions matching this event."""
        if not self._driver:
            return []
        query = """
        MATCH (pd:PlanDefinition {status: 'active'})-[:HAS_ACTION]->(a:Action)
        WHERE a.trigger_type = 'data-changed' AND a.trigger_name = $event_type
        OPTIONAL MATCH (a)-[:USES_DEFINITION]->(ad:ActivityDefinition)
        RETURN pd, a, ad
        ORDER BY pd.name, a.sequence
        """
        actions = []
        async with self._driver.session() as session:
            result = await session.run(query, event_type=event.event_type)
            async for record in result:
                actions.append(self._record_to_action(record))
        return actions

    async def _resolve_action(self, plan_id: str | None, action_id: str) -> ActionDefinition | None:
        """Resolve a single action by ID within a plan."""
        if not self._driver or not plan_id:
            return None
        query = """
        MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_ACTION]->(a:Action {id: $action_id})
        OPTIONAL MATCH (a)-[:USES_DEFINITION]->(ad:ActivityDefinition)
        RETURN a, ad
        """
        async with self._driver.session() as session:
            result = await session.run(query, plan_id=plan_id, action_id=action_id)
            record = await result.single()
            if not record:
                return None
            return self._record_to_action(record)

    @staticmethod
    def _record_to_action(record) -> ActionDefinition:
        """Convert a Neo4j record into an ActionDefinition."""
        action_node = record["a"]
        ad_node = record["ad"]
        config: dict[str, Any] = {}
        if ad_node and ad_node.get("dynamicValues"):
            try:
                config = json.loads(ad_node["dynamicValues"])
            except (json.JSONDecodeError, TypeError):
                pass
        return ActionDefinition(
            action_id=action_node["id"],
            subgraph_id=ad_node["subgraphId"] if ad_node else action_node.get("subgraphId", ""),
            trigger_type=action_node.get("trigger_type", ""),
            trigger_name=action_node.get("trigger_name", ""),
            condition=action_node.get("condition"),
            config=config,
            related_actions=action_node.get("relatedActions", []),
            sequence=int(action_node.get("sequence", 0)),
        )

    async def _write_audit_event(
        self, event: WorkflowEvent, steps: list[StepResult],
        status: str, pipeline_state: dict[str, Any],
    ) -> None:
        """Write a PipelineRun AuditEvent to the patient graph."""
        if not self._driver:
            return
        try:
            total_ms = sum(s.duration_ms for s in steps)
            entity_count = len(pipeline_state.get("entities") or [])
            errors = pipeline_state.get("errors") or []
            audit = {
                "id": f"audit-{event.run_id}",
                "type": "PipelineRun",
                "plan_definition_id": event.plan_definition_id or "",
                "patient_id": event.patient_id,
                "encounter_id": event.encounter_id or "",
                "run_id": event.run_id,
                "event_type": event.event_type,
                "status": status,
                "total_duration_ms": total_ms,
                "entity_count": entity_count,
                "error_count": len(errors),
                "steps": json.dumps([
                    {
                        "action_id": s.action_id,
                        "subgraph_id": s.subgraph_id,
                        "status": s.status,
                        "duration_ms": s.duration_ms,
                        "entity_count": s.entity_count,
                        "is_verified": s.is_verified,
                        "error": s.error,
                    }
                    for s in steps
                ]),
                "errors": json.dumps(errors[:50]),
            }
            query = """
            MERGE (ae:AuditEvent {id: $id})
            SET ae += $props,
                ae.created_at = datetime()
            WITH ae
            OPTIONAL MATCH (p:Patient {id: $patient_id})
            FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
                MERGE (ae)-[:AUDIT_FOR]->(p)
            )
            """
            async with self._driver.session() as session:
                await session.run(query, id=audit["id"], props=audit, patient_id=event.patient_id)
            logger.info(
                "AuditEvent %s written: status=%s entities=%d duration=%dms",
                audit["id"], status, entity_count, total_ms,
            )
        except Exception as exc:
            logger.warning("Failed to write AuditEvent: %s", exc)
