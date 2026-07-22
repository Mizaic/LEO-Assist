"""Tests for the universal durable step contract (M2.0)."""

from __future__ import annotations

import pytest

from libs.workflow.durable_steps import StepResult
from libs.workflow.step_contract import (
    CONTRACT_VERSION,
    ExecutionContext,
    StepBudgets,
    StepProvenance,
    envelope_step_result,
    execution_context_from_request,
)
from libs.workflow.durable_steps import StepRequest


def test_contract_version_is_semver_like() -> None:
    assert CONTRACT_VERSION.count(".") >= 1


def test_execution_context_round_trip_dict() -> None:
    ctx = ExecutionContext(
        policy_version="v3",
        plan_version_id="ver-uuid-1",
        capability_id="extraction",
        side_effect_class="write_patient",
        budgets=StepBudgets(max_llm_tokens=50000, max_duration_ms=120000),
    )
    restored = ExecutionContext.from_dict(ctx.to_dict())
    assert restored.policy_version == "v3"
    assert restored.plan_version_id == "ver-uuid-1"
    assert restored.capability_id == "extraction"
    assert restored.side_effect_class == "write_patient"
    assert restored.budgets.max_llm_tokens == 50000


def test_execution_context_from_request_uses_policy_version() -> None:
    request = StepRequest.from_message(
        {
            "event_type": "durable_step",
            "run_id": "run-1",
            "workflow_id": "pd-referral-assessment",
            "step_id": "act-a",
            "patient_id": "p-1",
            "policy_version": "v2",
            "plan_version_id": "ver-2",
        }
    )
    ctx = execution_context_from_request(request, capability_id="sbar")
    assert ctx.policy_version == "v2"
    assert ctx.plan_version_id == "ver-2"
    assert ctx.capability_id == "sbar"
    assert ctx.contract_version == CONTRACT_VERSION


def test_envelope_step_result_attaches_provenance() -> None:
    raw = StepResult(status="completed", output={"entities": []})
    provenance = StepProvenance(
        capability_id="extraction",
        capability_type="subgraph",
        input_schema_version="1",
        output_schema_version="1",
        side_effect_class="write_patient",
    )
    wrapped = envelope_step_result(raw, provenance)
    assert wrapped.status == "completed"
    assert wrapped.provenance["capability_id"] == "extraction"
    assert wrapped.provenance["contract_version"] == CONTRACT_VERSION
    assert wrapped.provenance["side_effect_class"] == "write_patient"


def test_envelope_rejects_missing_status() -> None:
    with pytest.raises(ValueError, match="status"):
        envelope_step_result(
            StepResult(status=""),  # type: ignore[arg-type]
            StepProvenance(capability_id="x"),
        )
