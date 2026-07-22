"""Tests for capability metadata registry (M2.0a)."""

from __future__ import annotations

from libs.pipeline_graph.capability_registry import (
    CapabilityMetadata,
    CapabilityRegistry,
    validate_plan_snapshot,
)


def test_register_and_lookup_capability() -> None:
    reg = CapabilityRegistry()
    reg.register(
        "extraction",
        CapabilityMetadata(
            capability_id="extraction",
            side_effect_class="write_patient",
            retry_class="idempotent",
            input_schema_version="1",
            output_schema_version="1",
        ),
    )
    meta = reg.get("extraction")
    assert meta.side_effect_class == "write_patient"
    assert meta.retry_class == "idempotent"


def test_validate_plan_snapshot_rejects_unregistered_subgraph() -> None:
    reg = CapabilityRegistry()
    reg.register(
        "extraction",
        CapabilityMetadata(capability_id="extraction"),
    )
    plan = {
        "action": [
            {"id": "a1", "_subgraphId": "extraction"},
            {"id": "a2", "_subgraphId": "unknown_subgraph"},
        ]
    }
    errors = validate_plan_snapshot(plan, registry=reg)
    assert any("unknown_subgraph" in err for err in errors)


def test_validate_plan_snapshot_accepts_builtin_node_types() -> None:
    reg = CapabilityRegistry()
    plan = {
        "action": [
            {"id": "t1", "_subgraphId": "trigger", "_nodeType": "trigger"},
            {"id": "c1", "_subgraphId": "condition", "_nodeType": "condition"},
        ]
    }
    assert validate_plan_snapshot(plan, registry=reg) == []


def test_validate_plan_snapshot_accepts_registered_subgraph() -> None:
    reg = CapabilityRegistry()
    reg.register("sbar", CapabilityMetadata(capability_id="sbar"))
    plan = {"action": [{"id": "s1", "_subgraphId": "sbar"}]}
    assert validate_plan_snapshot(plan, registry=reg) == []
