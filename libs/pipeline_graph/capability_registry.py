"""Capability metadata registry for pipeline subgraphs (M2.0a).

Atlas trace:
  DO: DO-13EEC645
  DI: DI-5D0F6FBA
  Risks: R-77D2EB0C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-13EEC645")

Each registered subgraph exposes side-effect class, schema versions and retry
semantics so plan publication can reject incompatible workflow steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libs.workflow.step_contract import RetryClass, SideEffectClass


@dataclass(frozen=True)
class CapabilityMetadata:
    capability_id: str
    capability_type: str = "subgraph"
    input_schema_version: str = "1"
    output_schema_version: str = "1"
    side_effect_class: SideEffectClass = "read_only"
    retry_class: RetryClass = "idempotent"
    default_timeout_ms: int = 3_600_000


_BUILTIN_CAPABILITIES: dict[str, CapabilityMetadata] = {
    "trigger": CapabilityMetadata(
        capability_id="trigger",
        capability_type="control",
        side_effect_class="none",
        retry_class="idempotent",
    ),
    "condition": CapabilityMetadata(
        capability_id="condition",
        capability_type="control",
        side_effect_class="read_only",
        retry_class="idempotent",
    ),
}


class CapabilityRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, CapabilityMetadata] = dict(_BUILTIN_CAPABILITIES)

    def register(self, capability_id: str, metadata: CapabilityMetadata) -> None:
        self._entries[capability_id] = metadata

    def get(self, capability_id: str) -> CapabilityMetadata:
        if capability_id not in self._entries:
            raise KeyError(f"Capability '{capability_id}' is not registered")
        return self._entries[capability_id]

    def has(self, capability_id: str) -> bool:
        return capability_id in self._entries

    def list_capabilities(self) -> list[CapabilityMetadata]:
        return [self._entries[k] for k in sorted(self._entries)]


_default_capability_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _default_capability_registry
    if _default_capability_registry is None:
        _default_capability_registry = _build_default_registry()
    return _default_capability_registry


def _side_effect_for_subgraph(subgraph_id: str) -> SideEffectClass:
    if subgraph_id in {"persist", "episode_engine", "staging_enrichment"}:
        return "write_patient"
    if subgraph_id in {"queue_publish", "rest_connector"}:
        return "publish_event"
    if subgraph_id in {"human_review_gate", "hitl_ner_queue", "hitl_coding_queue"}:
        return "human_gate"
    if subgraph_id in {"guidance_rule_extraction"}:
        return "write_knowledge"
    return "read_only"


def _build_default_registry() -> CapabilityRegistry:
    from libs.pipeline_graph.registry import get_registry

    reg = CapabilityRegistry()
    for item in get_registry().list_subgraphs():
        sid = str(item.get("id") or "")
        if not sid or reg.has(sid):
            continue
        reg.register(
            sid,
            CapabilityMetadata(
                capability_id=sid,
                side_effect_class=_side_effect_for_subgraph(sid),
            ),
        )
    return reg


def _action_capability_id(action: dict[str, Any]) -> str:
    node_type = str(action.get("_nodeType") or action.get("nodeType") or "")
    subgraph_id = str(action.get("_subgraphId") or action.get("subgraphId") or "")
    if node_type in {"trigger", "condition"}:
        return node_type
    return subgraph_id or node_type or str(action.get("id") or "")


def validate_plan_snapshot(
    plan_resource: dict[str, Any],
    *,
    registry: CapabilityRegistry | None = None,
) -> list[str]:
    """Return validation errors for unregistered plan action capabilities."""
    from libs.workflow.referral_policy import (
        parse_referral_policy,
        referral_policy_requires_validation,
        validate_referral_policy,
    )

    reg = registry or get_capability_registry()
    errors: list[str] = []
    if referral_policy_requires_validation(plan_resource):
        if plan_resource.get("_referralPolicy") is None:
            errors.append("referral assessment plan requires _referralPolicy")
        else:
            errors.extend(
                validate_referral_policy(parse_referral_policy(plan_resource))
            )
    actions = plan_resource.get("action") or plan_resource.get("actions") or []
    if not isinstance(actions, list):
        return ["plan action list is invalid"]
    for action in actions:
        if not isinstance(action, dict):
            errors.append("plan action entry is not an object")
            continue
        cap_id = _action_capability_id(action)
        action_id = str(action.get("id") or cap_id)
        if not cap_id:
            errors.append(f"action '{action_id}' has no capability id")
            continue
        if not reg.has(cap_id):
            errors.append(
                f"action '{action_id}' references unregistered capability '{cap_id}'"
            )
    return errors
