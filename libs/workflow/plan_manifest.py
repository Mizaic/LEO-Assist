"""Pinned PlanDefinitionVersion manifest loading (M2.1).

Runs execute against immutable PlanDefinitionVersion snapshots, not live
PlanDefinition / ActivityDefinition nodes that may change mid-flight.

Atlas trace:
  DI: DI-B1E43400
  DO: DO-3F7F7B7D
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B1E43400")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.workflow.referral_policy import parse_referral_policy

logger = logging.getLogger(__name__)

_SUBGRAPH_IMPLIES_NODE_TYPE = {"condition": "condition", "trigger": "trigger"}


@dataclass
class PlanAction:
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


@dataclass(frozen=True)
class PlanManifest:
    plan_id: str
    version_id: int
    version_node_id: str
    policy_version: str
    workflow_mode: str
    actions: tuple[PlanAction, ...]
    referral_policy: dict[str, Any] = field(default_factory=dict)

    def action_map(self) -> dict[str, PlanAction]:
        return {action.action_id: action for action in self.actions}


def policy_version_label(version_id: int) -> str:
    return f"v{int(version_id)}"


_LOAD_VERSION_QUERY = """
MATCH (pd:PlanDefinition {id: $plan_id})-[:HAS_VERSION]->(v:PlanDefinitionVersion)
WHERE $policy_version IN ['latest', 'default']
   OR toString(v.versionId) = $policy_version
   OR v.id = $policy_version
   OR ('v' + toString(v.versionId)) = $policy_version
RETURN v.id AS version_node_id,
       v.versionId AS version_id,
       v.rawJson AS raw_json,
       coalesce(v.workflowMode, pd.workflowMode, '') AS workflow_mode
ORDER BY v.versionId DESC
LIMIT 1
"""

_LOAD_PINNED_QUERY = """
MATCH (r:PipelineRun {id: $run_id})-[:USED_WORKFLOW]->(v:PlanDefinitionVersion)
RETURN v.id AS version_node_id,
       v.versionId AS version_id,
       v.rawJson AS raw_json,
       coalesce(v.planId, r.plan_definition_id, '') AS plan_id,
       coalesce(v.workflowMode, '') AS workflow_mode
LIMIT 1
"""


def _parse_trigger_name(action: dict[str, Any]) -> str:
    trigger = (action.get("trigger") or [{}])[0]
    name = trigger.get("name", "")
    if isinstance(name, list):
        return str(name[0]) if name else ""
    return str(name) if name else ""


def _fhir_action_to_plan_action(action: dict[str, Any]) -> PlanAction:
    config: dict[str, Any] = {}
    dynamic = action.get("_dynamicValues")
    if isinstance(dynamic, dict):
        config = dict(dynamic)
    related_defs = action.get("relatedAction") or []
    related_ids = [
        rel.get("actionId", "")
        for rel in related_defs
        if isinstance(rel, dict) and rel.get("actionId")
    ]
    related_edges = action.get("relatedActionEdges")
    if not related_edges:
        related_edges = [
            {
                "actionId": rel.get("actionId", ""),
                "relationship": rel.get("relationship", "after-end"),
                "sourceHandle": rel.get("sourceHandle"),
                "targetHandle": rel.get("targetHandle"),
            }
            for rel in related_defs
            if isinstance(rel, dict) and rel.get("actionId")
        ]
    subgraph_id = str(action.get("_subgraphId") or action.get("subgraphId") or "")
    implied = _SUBGRAPH_IMPLIES_NODE_TYPE.get(subgraph_id)
    node_type = str(action.get("_nodeType") or action.get("nodeType") or "")
    if implied is not None:
        node_type = implied
    elif not node_type:
        node_type = "action"
    return PlanAction(
        action_id=str(action.get("id") or ""),
        subgraph_id=subgraph_id,
        node_type=node_type,
        config=config,
        related_actions=related_ids or related_defs,
        related_edges=list(related_edges or []),
        sequence=int(action.get("_sequence") or action.get("sequence") or 0),
        trigger_name=_parse_trigger_name(action),
        completion_queue=str(action.get("completionQueue") or ""),
        completion_event_type=str(
            action.get("_durableEventType") or action.get("durableEventType") or ""
        ),
    )


def parse_actions_from_snapshot(plan_resource: dict[str, Any]) -> list[PlanAction]:
    raw_actions = plan_resource.get("action") or plan_resource.get("actions") or []
    actions = [
        _fhir_action_to_plan_action(item)
        for item in raw_actions
        if isinstance(item, dict)
    ]
    return sorted(actions, key=lambda item: item.sequence)


def _manifest_from_row(row: dict[str, Any], *, plan_id: str) -> PlanManifest:
    raw_json = row.get("raw_json") or ""
    if isinstance(raw_json, dict):
        resource = raw_json
    else:
        resource = json.loads(raw_json)
    version_id = int(row.get("version_id") or 0)
    workflow_mode = str(row.get("workflow_mode") or resource.get("_workflowMode") or "")
    return PlanManifest(
        plan_id=plan_id or str(resource.get("id") or ""),
        version_id=version_id,
        version_node_id=str(row.get("version_node_id") or ""),
        policy_version=policy_version_label(version_id),
        workflow_mode=workflow_mode,
        actions=tuple(parse_actions_from_snapshot(resource)),
        referral_policy=parse_referral_policy(resource),
    )


def load_plan_manifest(
    plan_id: str,
    policy_version: str = "latest",
) -> PlanManifest:
    """Load the pinned workflow snapshot for a plan id and policy version."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            _LOAD_VERSION_QUERY,
            plan_id=plan_id,
            policy_version=policy_version or "latest",
        )
        if not rows:
            raise ValueError(
                f"No PlanDefinitionVersion for plan '{plan_id}' "
                f"policy_version='{policy_version}'"
            )
        return _manifest_from_row(rows[0], plan_id=plan_id)
    finally:
        client.close()


def load_pinned_manifest(run_id: str, *, client: Any | None = None) -> PlanManifest:
    """Load the manifest pinned on a PipelineRun via USED_WORKFLOW."""
    owns_client = client is None
    pg = client or PatientGraphClient()
    try:
        rows = pg.run(_LOAD_PINNED_QUERY, run_id=run_id)
        if not rows:
            raise ValueError(f"PipelineRun '{run_id}' has no pinned workflow version")
        row = rows[0]
        return _manifest_from_row(row, plan_id=str(row.get("plan_id") or ""))
    finally:
        if owns_client:
            pg.close()


def resolve_policy_version(body: dict[str, Any]) -> str:
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    for source in (body, ctx or {}):
        if not isinstance(source, dict):
            continue
        explicit = source.get("policy_version")
        if explicit:
            return str(explicit)
    return "latest"


def load_manifest_for_run(
    run_id: str,
    plan_id: str,
    policy_version: str,
    *,
    client: Any | None = None,
) -> PlanManifest:
    """Prefer the run-pinned snapshot; fall back to policy version lookup."""
    owns_client = client is None
    pg = client or PatientGraphClient()
    try:
        rows = pg.run(_LOAD_PINNED_QUERY, run_id=run_id)
        if rows:
            return _manifest_from_row(rows[0], plan_id=plan_id)
    except Exception:
        logger.debug(
            "Pinned manifest lookup failed for run_id=%s", run_id, exc_info=True
        )
    finally:
        if owns_client:
            pg.close()
    return load_plan_manifest(plan_id, policy_version)


_LOAD_WORKFLOW_MODE_QUERY = """
MATCH (pd:PlanDefinition {id: $plan_id})
RETURN coalesce(pd.workflowMode, '') AS workflow_mode
LIMIT 1
"""

_seed_workflow_modes: dict[str, str] | None = None


def _load_seed_workflow_modes() -> dict[str, str]:
    """Load workflowMode values from seed_plan_definitions (offline fallback)."""
    global _seed_workflow_modes
    if _seed_workflow_modes is not None:
        return _seed_workflow_modes
    modes: dict[str, str] = {}
    try:
        import importlib.util
        import os
        import sys

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        scripts_dir = os.path.join(repo_root, "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        spec = importlib.util.spec_from_file_location(
            "seed_plan_definitions",
            os.path.join(scripts_dir, "seed_plan_definitions.py"),
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plan_sources = list(getattr(mod, "PLAN_DEFINITIONS", []) or [])
            validation_loader = getattr(mod, "all_validation_plan_definitions", None)
            if callable(validation_loader):
                plan_sources.extend(validation_loader())
            for plan in plan_sources:
                plan_id = str(plan.get("id") or "")
                mode = str(plan.get("_workflowMode") or "")
                if plan_id and mode:
                    modes[plan_id] = mode
    except Exception:
        logger.debug("Seed workflow mode lookup failed", exc_info=True)
    _seed_workflow_modes = modes
    return modes


def resolve_plan_workflow_mode(plan_id: str) -> str:
    """Return workflowMode for a plan (seed durable cutover, then KG, then seed)."""
    if not plan_id:
        return ""
    seed_mode = _load_seed_workflow_modes().get(plan_id, "")
    if seed_mode == "durable_pubsub":
        return seed_mode
    kg_mode = ""
    try:
        client = KnowledgeGraphClient()
        try:
            rows = client.run(_LOAD_WORKFLOW_MODE_QUERY, plan_id=plan_id)
            if rows:
                kg_mode = str(rows[0].get("workflow_mode") or "")
        finally:
            client.close()
    except Exception:
        logger.debug(
            "Knowledge Graph workflow mode lookup failed for plan_id=%s",
            plan_id,
            exc_info=True,
        )
    if kg_mode:
        return kg_mode
    return seed_mode
