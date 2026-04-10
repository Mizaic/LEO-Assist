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
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from libs.pipeline_graph.registry import get_registry

logger = logging.getLogger(__name__)

_ENTITY_KEY_ALIASES = {"processed_entities", "resolved_entities"}

HALT_SUBGRAPHS = frozenset()
_PIPELINE_PASSTHROUGH_SENTINEL = "__pipeline_passthrough__"
_ARRAY_PATH_RE = re.compile(r"^(?P<top>[A-Za-z0-9_]+)\[\]\.(?P<sub>[A-Za-z0-9_]+)$")


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
    node_type: str = "action"
    condition: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    related_actions: list[str] = field(default_factory=list)
    related_edges: list[dict[str, Any]] = field(default_factory=list)
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
    # LLM token counts harvested from subgraph output state
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_cached_tokens: int = 0
    llm_cost_usd: float = 0.0
    llm_prompt_name: str = ""
    llm_prompt_version: int = 0
    llm_prompt_hash: str = ""
    llm_provider: str = ""
    llm_model_tier: str = ""
    llm_few_shot_example_ids: list[str] = field(default_factory=list)


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

    async def handle_event(
        self,
        event: WorkflowEvent,
        step_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Execute the full pipeline chain for an event."""
        all_actions = await self._get_all_plan_actions(event.plan_definition_id) if (
            self._driver and event.plan_definition_id
        ) else await self._resolve_action_chain(event)
        if not all_actions:
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
        action_by_id = {a.action_id: a for a in all_actions}
        outgoing = self._build_outgoing_edges(all_actions)
        has_graph_edges = any(outgoing.values())
        trigger_ids = [
            a.action_id
            for a in all_actions
            if a.trigger_name == event.event_type or a.node_type == "trigger"
        ]
        if not trigger_ids:
            trigger_ids = [all_actions[0].action_id] if all_actions else []

        queue = list(trigger_ids)
        executed: set[str] = set()
        fallback_enqueued = False

        while queue:
            action_id = queue.pop(0)
            action = action_by_id.get(action_id)
            if not action or action_id in executed:
                continue
            executed.add(action_id)

            selected_port: str | None = None
            if action.node_type == "trigger":
                step_result = StepResult(
                    action_id=action.action_id,
                    subgraph_id=action.subgraph_id or "trigger",
                    status="completed",
                    duration_ms=0,
                    output={},
                )
            elif action.node_type == "condition":
                selected_port = self._evaluate_condition_port(action, pipeline_state)
                step_result = StepResult(
                    action_id=action.action_id,
                    subgraph_id=action.subgraph_id or "condition",
                    status="completed",
                    duration_ms=0,
                    output={"condition_port": selected_port},
                )
            else:
                step_state = self._build_step_state(action, pipeline_state)
                step_result = await self._execute_step(action, step_state)
            step_results.append(step_result)
            if step_callback:
                step_callback(
                    {
                        "type": "step_completed",
                        "run_id": event.run_id,
                        "patient_id": pipeline_state.get("patient_id"),
                        "encounter_id": pipeline_state.get("encounter_id"),
                        "action_id": step_result.action_id,
                        "subgraph_id": step_result.subgraph_id,
                        "status": step_result.status,
                        "duration_ms": step_result.duration_ms,
                        "entity_count": step_result.entity_count,
                        "error": step_result.error,
                    }
                )

            if step_result.status == "error":
                final_status = "error"
                logger.error("Pipeline halted at %s: %s",
                             action.action_id, step_result.error)
                break

            effective_output = self._apply_field_mappings_to_output(
                action, pipeline_state, step_result.output
            )
            step_result.output = effective_output
            self._merge_step_output(pipeline_state, effective_output)

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

            next_edges = outgoing.get(action.action_id, [])
            if action.node_type == "condition":
                default_ports = {"default", "else", "failed"}
                if selected_port:
                    selected = [e for e in next_edges if e.get("sourceHandle") == selected_port]
                    if not selected:
                        selected = [e for e in next_edges if (e.get("sourceHandle") or "").lower() in default_ports]
                    next_edges = selected

            if next_edges:
                next_targets = sorted(
                    (e.get("target") for e in next_edges if e.get("target")),
                    key=lambda tid: action_by_id.get(tid).sequence if action_by_id.get(tid) else 0,
                )
                queue.extend(next_targets)

            if not queue and not fallback_enqueued and (not has_graph_edges or len(executed) < len(all_actions)):
                remainder = sorted(
                    (a.action_id for a in all_actions if a.action_id not in executed),
                    key=lambda aid: action_by_id[aid].sequence,
                )
                queue.extend(remainder)
                fallback_enqueued = True

        await self._write_audit_event(event, step_results, final_status, pipeline_state)
        if step_callback:
            done_type = "run_error" if final_status == "error" else "run_completed"
            step_callback(
                {
                    "type": done_type,
                    "run_id": event.run_id,
                    "patient_id": pipeline_state.get("patient_id"),
                    "encounter_id": pipeline_state.get("encounter_id"),
                    "status": final_status,
                    "step_count": len(step_results),
                    "entity_count": len(pipeline_state.get("entities") or []),
                }
            )

        total_input   = sum(s.llm_input_tokens  for s in step_results)
        total_output  = sum(s.llm_output_tokens for s in step_results)
        total_cached  = sum(s.llm_cached_tokens for s in step_results)
        total_cost    = sum(s.llm_cost_usd      for s in step_results)

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
                    "llm_input_tokens":  sr.llm_input_tokens,
                    "llm_output_tokens": sr.llm_output_tokens,
                    "llm_cached_tokens": sr.llm_cached_tokens,
                    "llm_cost_usd":      round(sr.llm_cost_usd, 6),
                    "llm_prompt_name": sr.llm_prompt_name,
                    "llm_prompt_version": sr.llm_prompt_version,
                    "llm_prompt_hash": sr.llm_prompt_hash,
                    "llm_provider": sr.llm_provider,
                    "llm_model_tier": sr.llm_model_tier,
                    "llm_few_shot_example_ids": sr.llm_few_shot_example_ids,
                }
                for sr in step_results
            ],
            "entity_count": len(pipeline_state.get("entities") or []),
            "llm_usage": {
                "input_tokens":  total_input,
                "output_tokens": total_output,
                "cached_tokens": total_cached,
                "cost_usd":      round(total_cost, 6),
                    "per_step": [
                        {
                            "action_id": s.action_id,
                            "subgraph_id": s.subgraph_id,
                            "status": s.status,
                            "prompt_name": s.llm_prompt_name,
                            "prompt_version": s.llm_prompt_version,
                            "prompt_hash": s.llm_prompt_hash,
                            "provider": s.llm_provider,
                            "model_tier": s.llm_model_tier,
                            "few_shot_example_ids": s.llm_few_shot_example_ids,
                            "input_tokens": s.llm_input_tokens,
                            "output_tokens": s.llm_output_tokens,
                            "cached_tokens": s.llm_cached_tokens,
                            "cost_usd": round(s.llm_cost_usd, 6),
                        }
                        for s in step_results
                        if s.llm_input_tokens
                        or s.llm_output_tokens
                        or s.llm_cached_tokens
                        or s.llm_prompt_hash
                    ],
            },
        }

    @staticmethod
    def _build_outgoing_edges(actions: list[ActionDefinition]) -> dict[str, list[dict[str, Any]]]:
        outgoing: dict[str, list[dict[str, Any]]] = {}
        for action in actions:
            for edge in action.related_edges:
                source_id = edge.get("actionId")
                if not source_id:
                    continue
                outgoing.setdefault(source_id, []).append(
                    {
                        "target": action.action_id,
                        "sourceHandle": edge.get("sourceHandle"),
                        "targetHandle": edge.get("targetHandle"),
                    }
                )
        return outgoing

    @staticmethod
    def _resolve_state_value(path: str, state: dict[str, Any]) -> Any:
        if not path:
            return None
        cursor: Any = state
        for part in path.split("."):
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                return None
        return cursor

    def _evaluate_condition_port(self, action: ActionDefinition, state: dict[str, Any]) -> str:
        params = action.config.get("params", {}) if isinstance(action.config, dict) else {}
        rules = params.get("rules") or action.config.get("rules") or []
        default_port = str(params.get("defaultPort") or action.config.get("defaultPort") or "else")
        for rule in rules:
            field = str(rule.get("field") or "")
            operator = str(rule.get("operator") or "==")
            expected = rule.get("value")
            output_port = str(rule.get("outputPort") or "matched")
            actual = self._resolve_state_value(field, state)
            if self._rule_matches(actual, operator, expected):
                return output_port
        return default_port

    @staticmethod
    def _rule_matches(actual: Any, operator: str, expected: Any) -> bool:
        if operator == "exists":
            return actual is not None
        if operator == "contains":
            return expected is not None and actual is not None and str(expected) in str(actual)
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
        if action.subgraph_id == "queue_publish" and self._bus:
            try:
                from libs.message_bus.base import Message

                queue_name = str(state.get("queue_name") or "pipeline-jobs")
                message_body = state.get("message_body") or {}
                delay = int(state.get("schedule_after_seconds") or 0)
                await self._bus.send(
                    queue_name,
                    Message(body=message_body if isinstance(message_body, dict) else {"payload": message_body}),
                    schedule_after_seconds=delay if delay > 0 else None,
                )
                duration = int((time.monotonic() - t0) * 1000)
                return StepResult(
                    action_id=action.action_id,
                    subgraph_id=action.subgraph_id,
                    status="completed",
                    duration_ms=duration,
                    output={"queued": True},
                )
            except Exception as exc:
                duration = int((time.monotonic() - t0) * 1000)
                return StepResult(
                    action_id=action.action_id,
                    subgraph_id=action.subgraph_id,
                    status="error",
                    duration_ms=duration,
                    error=str(exc),
                )
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
            # Harvest token data written into subgraph state by LLM steps
            llm_tokens = result.get("llm_tokens") or {}
            few_shot_ids = llm_tokens.get("few_shot_example_ids") or []
            if not isinstance(few_shot_ids, list):
                few_shot_ids = []
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="completed",
                duration_ms=duration,
                entity_count=len(entities),
                is_verified=result.get("is_verified"),
                output=result,
                llm_input_tokens=int(llm_tokens.get("input_tokens", 0)),
                llm_output_tokens=int(llm_tokens.get("output_tokens", 0)),
                llm_cached_tokens=int(llm_tokens.get("cached_tokens", 0)),
                llm_cost_usd=float(llm_tokens.get("cost_usd", 0.0)),
                llm_prompt_name=str(llm_tokens.get("prompt_name") or ""),
                llm_prompt_version=int(llm_tokens.get("prompt_version") or 0),
                llm_prompt_hash=str(llm_tokens.get("prompt_hash") or ""),
                llm_provider=str(llm_tokens.get("provider") or ""),
                llm_model_tier=str(llm_tokens.get("model_tier") or ""),
                llm_few_shot_example_ids=[str(i) for i in few_shot_ids if i],
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
        params = action.config.get("params") if isinstance(action.config, dict) else None
        if isinstance(params, dict):
            state.update(params)

        # UI config keys are camelCase, subgraphs use snake_case.
        if "promptConfigId" in state and "prompt_config_id" not in state:
            state["prompt_config_id"] = state.get("promptConfigId")
        if "promptConfigName" in state and "prompt_config_name" not in state:
            state["prompt_config_name"] = state.get("promptConfigName")
        if "promptConfigVersion" in state and "prompt_config_version" not in state:
            state["prompt_config_version"] = state.get("promptConfigVersion")
        if "outputTarget" in state and "output_target" not in state:
            state["output_target"] = state.get("outputTarget")

        prompt_config_id = str(state.get("prompt_config_id") or "").strip()
        if prompt_config_id and "prompt_config" not in state:
            state["prompt_config"] = self._load_prompt_config(prompt_config_id)
        elif not prompt_config_id and "prompt_config" not in state:
            prompt_config_name = str(state.get("prompt_config_name") or "").strip()
            if prompt_config_name:
                try:
                    from libs.prompts.registry import get_prompt_config

                    prompt_config_version = int(state.get("prompt_config_version") or 1)
                    state["prompt_config"] = get_prompt_config(
                        prompt_config_name, version=prompt_config_version
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to load PromptConfig by name=%s version=%s: %s",
                        prompt_config_name,
                        state.get("prompt_config_version") or 1,
                        exc,
                    )

        return state

    @staticmethod
    def _merge_step_output(
        pipeline_state: dict[str, Any], step_output: dict[str, Any],
    ) -> None:
        """Merge a subgraph's output into the shared pipeline state.

        Normalises entity keys so all downstream steps find entities
        under the canonical ``entities`` key.

        Errors are accumulated, but subgraphs often pass through the errors
        they received (so downstream steps can inspect them). To prevent the
        same error being appended multiple times, only errors that do not
        already exist in pipeline_state are added.
        """
        for key, value in step_output.items():
            if key in _ENTITY_KEY_ALIASES and value:
                pipeline_state["entities"] = value
            elif key == "errors" and value:
                existing = list(pipeline_state.get("errors") or [])
                existing_set = set(existing)
                new_errors = [e for e in value if e not in existing_set]
                if new_errors:
                    pipeline_state["errors"] = existing + new_errors
            else:
                pipeline_state[key] = value

    @staticmethod
    def _parse_array_path(path: str) -> tuple[str, str] | None:
        match = _ARRAY_PATH_RE.match(path.strip())
        if not match:
            return None
        return match.group("top"), match.group("sub")

    @staticmethod
    def _extract_state_path_value(state: dict[str, Any], path: str) -> Any:
        parsed = WorkflowEngine._parse_array_path(path)
        if not parsed:
            return state.get(path)
        top_key, sub_field = parsed
        rows = state.get(top_key)
        if not isinstance(rows, list):
            return None
        values: list[Any] = []
        for row in rows:
            if isinstance(row, dict):
                values.append(row.get(sub_field))
            else:
                values.append(None)
        return values

    @staticmethod
    def _extract_output_field(output: dict[str, Any], llm_field: str) -> Any:
        parsed = WorkflowEngine._parse_array_path(llm_field)
        if not parsed:
            return output.get(llm_field)
        source_top, source_sub = parsed
        source_rows = output.get(source_top)
        # Extraction output uses entities[]; UI schema often calls this terms[].
        if not isinstance(source_rows, list) and source_top == "terms":
            source_rows = output.get("entities")
        if not isinstance(source_rows, list):
            return None
        values: list[Any] = []
        for row in source_rows:
            if isinstance(row, dict):
                values.append(row.get(source_sub))
            else:
                values.append(None)
        return values

    @staticmethod
    def _write_state_path_value(target: dict[str, Any], path: str, value: Any) -> None:
        parsed = WorkflowEngine._parse_array_path(path)
        if not parsed:
            target[path] = value
            return
        top_key, sub_field = parsed
        if isinstance(value, list):
            rows = target.get(top_key)
            if not isinstance(rows, list):
                rows = []
            if len(rows) < len(value):
                rows.extend({} for _ in range(len(value) - len(rows)))
            for idx, item_val in enumerate(value):
                if not isinstance(rows[idx], dict):
                    rows[idx] = {}
                rows[idx][sub_field] = item_val
            target[top_key] = rows
            return
        target[top_key] = value

    def _apply_field_mappings_to_output(
        self,
        action: ActionDefinition,
        pipeline_state: dict[str, Any],
        step_output: dict[str, Any],
    ) -> dict[str, Any]:
        config = action.config if isinstance(action.config, dict) else {}
        params = config.get("params") if isinstance(config.get("params"), dict) else {}
        mappings = params.get("field_mappings") or config.get("field_mappings") or []
        if not isinstance(mappings, list) or not mappings:
            return step_output

        mapped: dict[str, Any] = {}
        for row in mappings:
            if not isinstance(row, dict):
                continue
            state_path = str(row.get("statePath") or "").strip()
            if not state_path:
                continue
            llm_field = str(row.get("llmField") or "").strip()
            if llm_field == _PIPELINE_PASSTHROUGH_SENTINEL:
                passthrough_val = self._extract_state_path_value(pipeline_state, state_path)
                if passthrough_val is None:
                    continue
                self._write_state_path_value(mapped, state_path, passthrough_val)
                continue

            extracted_val = self._extract_output_field(step_output, llm_field)
            if extracted_val is None:
                continue
            self._write_state_path_value(mapped, state_path, extracted_val)

        if not mapped:
            return step_output
        merged = dict(step_output)
        merged.update(mapped)
        return merged

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
        from libs.message_bus.base import Message

        await self._bus.send(
            "pipeline-jobs",
            Message(
                body=message,
                correlation_id=patient_id,
                subject="timer",
            ),
            schedule_after_seconds=delay_seconds,
        )

    def _load_prompt_config(self, config_id: str) -> dict[str, Any]:
        """Load a PromptConfig from Neo4j by ID, returning a dict for subgraph state.

        PromptConfig nodes are in the Knowledge Graph, not the Patient Graph.
        """
        try:
            from libs.cypher.prompt_config_queries import GET_PROMPT
            from libs.neo4j_client.client import KnowledgeGraphClient

            client = KnowledgeGraphClient()
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
                        "outputSchema": row.get("outputSchema") or None,
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
        WHERE a.trigger_name = $event_type
          AND coalesce(a.trigger_type, 'data-changed') IN ['data-changed', 'admin-action']
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
        WHERE a.trigger_name = $event_type
          AND coalesce(a.trigger_type, 'data-changed') IN ['data-changed', 'admin-action']
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
        """Resolve a single action by canvas_id within a plan."""
        if not self._driver or not plan_id:
            return None
        query = """
        MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_ACTION]->(a:Action)
        WHERE a.canvas_id = $action_id
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
        related_edges_raw = action_node.get("relatedActionEdges")
        related_edges: list[dict[str, Any]] = []
        if related_edges_raw:
            try:
                related_edges = json.loads(related_edges_raw)
            except (json.JSONDecodeError, TypeError):
                related_edges = []
        # canvas_id is the original user-defined node ID used for routing.
        # Nodes saved before the scoped-id migration only have id; fall back
        # so those plans keep working until they are re-saved.
        action_id = action_node.get("canvas_id") or action_node["id"]
        return ActionDefinition(
            action_id=action_id,
            subgraph_id=ad_node["subgraphId"] if ad_node else action_node.get("subgraphId", ""),
            trigger_type=action_node.get("trigger_type", ""),
            trigger_name=action_node.get("trigger_name", ""),
            node_type=action_node.get("nodeType", "action"),
            condition=action_node.get("condition"),
            config=config,
            related_actions=action_node.get("relatedActions", []),
            related_edges=related_edges,
            sequence=int(action_node.get("sequence", 0)),
        )

    async def trace_run(
        self,
        actions: list[ActionDefinition],
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Dry-run the pipeline collecting all step snapshots at once.

        Delegates to ``trace_run_stream`` and collects every event.
        Use ``trace_run_stream`` directly for real-time SSE streaming.
        """
        step_traces: list[dict[str, Any]] = []
        final_status = "completed"
        final_state: dict[str, Any] = {}
        async for event in self.trace_run_stream(actions, initial_state):
            if event["type"] == "step_done":
                step_traces.append(event["step_trace"])
            elif event["type"] == "pipeline_done":
                final_status = event["status"]
                final_state = event["final_state"]
        return {"status": final_status, "steps": step_traces, "final_state": final_state}

    async def trace_run_stream(
        self,
        actions: list[ActionDefinition],
        initial_state: dict[str, Any],
    ):
        """Async generator — yields SSE-ready event dicts as each step executes.

        Event types:
          ``step_start``    — emitted just before a step runs (gives the canvas
                             time to highlight the node as "running").
          ``step_done``     — emitted when a step finishes; includes the full
                             StepTrace snapshot (input/output state, timing, error).
          ``pipeline_done`` — emitted once when the whole pipeline finishes.

        Does NOT write audit events.  Subgraphs honouring ``dry_run=True`` skip
        their Neo4j write phases.
        """
        import copy

        pipeline_state: dict[str, Any] = dict(initial_state)
        pipeline_state.setdefault("dry_run", True)
        pipeline_state.setdefault("errors", [])

        action_by_id = {a.action_id: a for a in actions}
        outgoing = self._build_outgoing_edges(actions)
        has_graph_edges = any(outgoing.values())

        trigger_ids = [a.action_id for a in actions if a.node_type == "trigger"]
        if not trigger_ids:
            trigger_ids = [actions[0].action_id] if actions else []

        queue: list[str] = list(trigger_ids)
        executed: set[str] = set()
        fallback_enqueued = False
        final_status = "completed"
        halted_step_id: str | None = None

        while queue:
            action_id = queue.pop(0)
            action = action_by_id.get(action_id)
            if not action or action_id in executed:
                continue
            executed.add(action_id)

            # Signal the canvas to light up this node as "running"
            yield {
                "type": "step_start",
                "step_id": action.action_id,
                "label": action.config.get("label", action.action_id),
                "subgraph_id": action.subgraph_id or action.node_type,
                "node_type": action.node_type,
            }

            input_snap = self._sanitize_state(copy.deepcopy(pipeline_state))

            if action.node_type == "trigger":
                trace: dict[str, Any] = {
                    "step_id": action.action_id,
                    "subgraph_id": action.subgraph_id or "trigger",
                    "label": action.config.get("label", action.action_id),
                    "node_type": "trigger",
                    "input_state": input_snap,
                    "output_state": input_snap,
                    "duration_ms": 0,
                    "error": None,
                    "status": "completed",
                }

            elif action.node_type == "condition":
                selected_port = self._evaluate_condition_port(action, pipeline_state)
                pipeline_state["condition_port"] = selected_port
                out_snap = self._sanitize_state(copy.deepcopy(pipeline_state))
                trace = {
                    "step_id": action.action_id,
                    "subgraph_id": action.subgraph_id or "condition",
                    "label": action.config.get("label", action.action_id),
                    "node_type": "condition",
                    "input_state": input_snap,
                    "output_state": out_snap,
                    "duration_ms": 0,
                    "error": None,
                    "status": "completed",
                }

            else:
                step_state = self._build_step_state(action, pipeline_state)
                step_result = await self._execute_step(action, step_state)
                if step_result.status != "error":
                    effective_output = self._apply_field_mappings_to_output(
                        action, pipeline_state, step_result.output
                    )
                    step_result.output = effective_output
                    self._merge_step_output(pipeline_state, effective_output)
                else:
                    final_status = "error"

                # Verification quality gate: halt the pipeline when is_verified=False.
                # This mirrors the non-stream run() path and must fire in dry_run/probe
                # mode too so the canvas accurately reflects real-world behaviour.
                halt_reason: str | None = None
                if step_result.status != "error" and action.subgraph_id == "verification":
                    if not pipeline_state.get("is_verified", True):
                        halt_reason = "verification_failed"
                        final_status = "needs_review"
                        halted_step_id = action.action_id
                        logger.info(
                            "trace_run_stream: verification halted pipeline at step %s",
                            action.action_id,
                        )

                out_snap = self._sanitize_state(copy.deepcopy(pipeline_state))
                trace = {
                    "step_id": action.action_id,
                    "subgraph_id": action.subgraph_id,
                    "label": action.config.get("label", action.action_id),
                    "node_type": "action",
                    "input_state": input_snap,
                    "output_state": out_snap,
                    "duration_ms": step_result.duration_ms,
                    "error": step_result.error,
                    # "halted" is a distinct status from "error": the step itself
                    # ran fine but the quality gate decided to stop the pipeline.
                    "status": "halted" if halt_reason else step_result.status,
                    **({"halt_reason": halt_reason} if halt_reason else {}),
                }

            yield {"type": "step_done", "step_trace": trace}

            if trace["status"] in ("error", "halted"):
                break

            next_edges = outgoing.get(action_id, [])
            selected_port_val = (
                pipeline_state.get("condition_port") if action.node_type == "condition" else None
            )
            if action.node_type == "condition" and selected_port_val:
                default_ports = {"default", "else", "failed"}
                selected = [e for e in next_edges if e.get("sourceHandle") == selected_port_val]
                if not selected:
                    selected = [
                        e for e in next_edges
                        if (e.get("sourceHandle") or "").lower() in default_ports
                    ]
                next_edges = selected

            if next_edges:
                next_targets = sorted(
                    (e.get("target") for e in next_edges if e.get("target")),
                    key=lambda tid: action_by_id.get(tid).sequence if action_by_id.get(tid) else 0,
                )
                queue.extend(next_targets)

            if not queue and not fallback_enqueued and (
                not has_graph_edges or len(executed) < len(actions)
            ):
                remainder = sorted(
                    (a.action_id for a in actions if a.action_id not in executed),
                    key=lambda aid: action_by_id[aid].sequence,
                )
                queue.extend(remainder)
                fallback_enqueued = True

        yield {
            "type": "pipeline_done",
            "status": final_status,
            "halted_step_id": halted_step_id,
            "final_state": self._sanitize_state(dict(pipeline_state)),
        }

    @staticmethod
    def _sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
        """Trim large values so trace payloads stay API-friendly."""
        MAX_STR = 2000
        SKIP = {"prompt_config"}
        result: dict[str, Any] = {}
        for k, v in state.items():
            if k in SKIP:
                continue
            if isinstance(v, str) and len(v) > MAX_STR:
                result[k] = v[:MAX_STR] + " …[truncated]"
            elif isinstance(v, list) and len(v) > 100:
                result[k] = v[:100]
            else:
                result[k] = v
        return result

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
            total_input  = sum(s.llm_input_tokens  for s in steps)
            total_output = sum(s.llm_output_tokens for s in steps)
            total_cached = sum(s.llm_cached_tokens for s in steps)
            total_cost   = round(sum(s.llm_cost_usd for s in steps), 6)

            # Identify the extraction step for flat analytics fields.
            # Prefer the step whose subgraph_id is "extraction"; fall back to
            # the first step that has a prompt name set.
            extraction_step = next(
                (s for s in steps if s.subgraph_id == "extraction"),
                next((s for s in steps if s.llm_prompt_name), None),
            )

            first_error: str | None = None
            for s in steps:
                if s.error:
                    first_error = str(s.error)[:400]
                    break
            if not first_error and errors:
                first_error = str(errors[0])[:400]

            audit = {
                # ----------------------------------------------------------------
                # Identity
                # ----------------------------------------------------------------
                "id": f"audit-{event.run_id}",
                "type": "PipelineRun",
                "plan_definition_id": event.plan_definition_id or "",
                "patient_id": event.patient_id,
                "encounter_id": event.encounter_id or "",
                "run_id": event.run_id,
                "event_type": event.event_type,
                # ----------------------------------------------------------------
                # Run-level outcome (flat -- usable in Cypher WHERE / aggregation)
                # ----------------------------------------------------------------
                "status": status,
                "step_count": len(steps),
                "total_duration_ms": total_ms,
                "entity_count": entity_count,
                "error_count": len(errors),
                "first_error": first_error,
                # ----------------------------------------------------------------
                # LLM spend totals (flat -- used by ORG_SPEND_SUMMARY et al.)
                # ----------------------------------------------------------------
                "llm_input_tokens":  total_input,
                "llm_output_tokens": total_output,
                "llm_cached_tokens": total_cached,
                "llm_cost_usd":      total_cost,
                # ----------------------------------------------------------------
                # Primary extraction step dimensions (flat -- index + query on)
                # Enables: "empty_extraction rate by prompt version",
                #          "cost per entity by provider", regression gates.
                # ----------------------------------------------------------------
                "extraction_prompt_name":    (extraction_step.llm_prompt_name    if extraction_step else ""),
                "extraction_prompt_version": (extraction_step.llm_prompt_version if extraction_step else 0),
                "extraction_prompt_hash":    (extraction_step.llm_prompt_hash    if extraction_step else ""),
                "extraction_provider":       (extraction_step.llm_provider       if extraction_step else ""),
                "extraction_model_tier":     (extraction_step.llm_model_tier     if extraction_step else ""),
                # ----------------------------------------------------------------
                # Detail blobs (JSON strings -- for display / export, NOT analytics)
                # steps: full per-step trace for audit trail UI
                # errors: up to 50 error messages for diagnosis
                # llm_prompt_hashes: sorted deduplicated set, for exact prompt audit
                # ----------------------------------------------------------------
                "steps": json.dumps([
                    {
                        "action_id": s.action_id,
                        "subgraph_id": s.subgraph_id,
                        "status": s.status,
                        "duration_ms": s.duration_ms,
                        "entity_count": s.entity_count,
                        "is_verified": s.is_verified,
                        "error": s.error,
                        "llm_input_tokens":  s.llm_input_tokens,
                        "llm_output_tokens": s.llm_output_tokens,
                        "llm_cached_tokens": s.llm_cached_tokens,
                        "llm_cost_usd":      round(s.llm_cost_usd, 6),
                        "llm_prompt_name": s.llm_prompt_name,
                        "llm_prompt_version": s.llm_prompt_version,
                        "llm_prompt_hash": s.llm_prompt_hash,
                        "llm_provider": s.llm_provider,
                        "llm_model_tier": s.llm_model_tier,
                        "llm_few_shot_example_ids": s.llm_few_shot_example_ids,
                    }
                    for s in steps
                ]),
                "errors": json.dumps(errors[:50]),
                "llm_prompt_hashes": json.dumps(
                    sorted({s.llm_prompt_hash for s in steps if s.llm_prompt_hash})
                ),
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
