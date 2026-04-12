from __future__ import annotations

import pytest

from libs.workflow.engine import (
    ActionDefinition,
    StepResult,
    WorkflowEngine,
    WorkflowEvent,
)


def _edge(source: str) -> list[dict[str, str]]:
    return [{"actionId": source, "relationship": "after-end"}]


@pytest.mark.asyncio
async def test_handle_event_continues_to_extraction_check_on_empty_extraction(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = WorkflowEngine()
    actions = [
        ActionDefinition(
            action_id="start",
            subgraph_id="trigger",
            trigger_type="data-changed",
            trigger_name="encounter-created",
            node_type="trigger",
            sequence=0,
        ),
        ActionDefinition(
            action_id="extract",
            subgraph_id="extraction",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("start"),
            sequence=1,
        ),
        ActionDefinition(
            action_id="extraction-check",
            subgraph_id="extraction_check",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("extract"),
            sequence=2,
        ),
    ]

    async def _resolve_action_chain(_event: WorkflowEvent):
        return actions

    async def _execute_step(action: ActionDefinition, _state: dict):
        if action.subgraph_id == "extraction":
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="completed",
                output={"entities": []},
            )
        if action.subgraph_id == "extraction_check":
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="completed",
                output={"entities": [{"text": "shortness of breath"}]},
            )
        raise AssertionError(f"Unexpected action executed: {action.action_id}")

    async def _noop_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(engine, "_resolve_action_chain", _resolve_action_chain)
    monkeypatch.setattr(engine, "_execute_step", _execute_step)
    monkeypatch.setattr(engine, "_write_audit_event", _noop_audit)

    result = await engine.handle_event(
        WorkflowEvent(
            event_type="encounter-created",
            patient_id="p-1",
            encounter_id="e-1",
        )
    )

    assert result["status"] == "completed"
    assert result["entity_count"] == 1
    assert [step["action_id"] for step in result["steps"]] == [
        "start",
        "extract",
        "extraction-check",
    ]


@pytest.mark.asyncio
async def test_handle_event_still_aborts_without_extraction_check(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = WorkflowEngine()
    actions = [
        ActionDefinition(
            action_id="start",
            subgraph_id="trigger",
            trigger_type="data-changed",
            trigger_name="encounter-created",
            node_type="trigger",
            sequence=0,
        ),
        ActionDefinition(
            action_id="extract",
            subgraph_id="extraction",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("start"),
            sequence=1,
        ),
        ActionDefinition(
            action_id="terminology",
            subgraph_id="terminology",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("extract"),
            sequence=2,
        ),
    ]

    async def _resolve_action_chain(_event: WorkflowEvent):
        return actions

    async def _execute_step(action: ActionDefinition, _state: dict):
        if action.subgraph_id == "extraction":
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="completed",
                output={"entities": []},
            )
        raise AssertionError(
            f"Action should not execute after empty extraction: {action.action_id}"
        )

    async def _noop_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(engine, "_resolve_action_chain", _resolve_action_chain)
    monkeypatch.setattr(engine, "_execute_step", _execute_step)
    monkeypatch.setattr(engine, "_write_audit_event", _noop_audit)

    result = await engine.handle_event(
        WorkflowEvent(
            event_type="encounter-created",
            patient_id="p-1",
            encounter_id="e-1",
        )
    )

    assert result["status"] == "empty_extraction"
    assert [step["action_id"] for step in result["steps"]] == ["start", "extract"]
