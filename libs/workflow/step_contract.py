"""Universal durable step contract (M2.0).

Atlas trace:
  DO: DO-13EEC645
  DI: DI-5D0F6FBA
  Risks: R-77D2EB0C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-13EEC645")

Versioned envelope for execution context, provenance, side effects and budgets.
Every capability returns the same status/provenance shape via envelope_step_result().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from libs.workflow.durable_steps import StepRequest, StepResult

CONTRACT_VERSION = "1.0"

SideEffectClass = Literal[
    "none",
    "read_only",
    "write_patient",
    "write_knowledge",
    "publish_event",
    "human_gate",
]

RetryClass = Literal["idempotent", "non_idempotent", "never"]

_BUILTIN_SIDE_EFFECTS: dict[str, SideEffectClass] = {
    "trigger": "none",
    "condition": "read_only",
}


@dataclass(frozen=True)
class StepBudgets:
    max_llm_tokens: int = 0
    max_duration_ms: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "max_llm_tokens": int(self.max_llm_tokens),
            "max_duration_ms": int(self.max_duration_ms),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "StepBudgets":
        data = raw or {}
        return cls(
            max_llm_tokens=int(data.get("max_llm_tokens") or 0),
            max_duration_ms=int(data.get("max_duration_ms") or 0),
        )


@dataclass(frozen=True)
class ExecutionContext:
    contract_version: str = CONTRACT_VERSION
    policy_version: str = "default"
    plan_version_id: str = ""
    capability_id: str = ""
    side_effect_class: SideEffectClass = "none"
    budgets: StepBudgets = field(default_factory=StepBudgets)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["budgets"] = self.budgets.to_dict()
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExecutionContext":
        return cls(
            contract_version=str(raw.get("contract_version") or CONTRACT_VERSION),
            policy_version=str(raw.get("policy_version") or "default"),
            plan_version_id=str(raw.get("plan_version_id") or ""),
            capability_id=str(raw.get("capability_id") or ""),
            side_effect_class=_coerce_side_effect(raw.get("side_effect_class")),
            budgets=StepBudgets.from_dict(raw.get("budgets")),
        )


@dataclass(frozen=True)
class StepProvenance:
    capability_id: str
    capability_type: str = "subgraph"
    input_schema_version: str = "1"
    output_schema_version: str = "1"
    side_effect_class: SideEffectClass = "read_only"
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, str]:
        return {
            "capability_id": self.capability_id,
            "capability_type": self.capability_type,
            "input_schema_version": self.input_schema_version,
            "output_schema_version": self.output_schema_version,
            "side_effect_class": self.side_effect_class,
            "contract_version": self.contract_version,
        }


def _coerce_side_effect(value: Any) -> SideEffectClass:
    if value in {
        "none",
        "read_only",
        "write_patient",
        "write_knowledge",
        "publish_event",
        "human_gate",
    }:
        return value  # type: ignore[return-value]
    return "none"


def execution_context_from_request(
    request: StepRequest,
    *,
    capability_id: str,
    side_effect_class: SideEffectClass | None = None,
) -> ExecutionContext:
    effect = side_effect_class or _BUILTIN_SIDE_EFFECTS.get(capability_id, "read_only")
    return ExecutionContext(
        policy_version=str(request.policy_version or "default"),
        plan_version_id=str(request.plan_version_id or ""),
        capability_id=capability_id,
        side_effect_class=effect,
    )


def envelope_step_result(
    result: StepResult,
    provenance: StepProvenance,
) -> StepResult:
    if not result.status:
        raise ValueError("StepResult.status is required")
    prov = provenance.to_dict()
    metrics = dict(result.metrics)
    metrics.setdefault("contract_version", CONTRACT_VERSION)
    return StepResult(
        status=result.status,
        output=result.output,
        output_refs=result.output_refs,
        warnings=result.warnings,
        errors=result.errors,
        metrics=metrics,
        provenance=prov,
        next_event_type=result.next_event_type,
        next_step_id=result.next_step_id,
    )
