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


def _plan_actions() -> list[ActionDefinition]:
    return [
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
            action_id="persist",
            subgraph_id="persist",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("extract"),
            sequence=2,
        ),
        ActionDefinition(
            action_id="anchor",
            subgraph_id="anchor_detect",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("persist"),
            sequence=3,
        ),
        ActionDefinition(
            action_id="episode",
            subgraph_id="episode_build",
            trigger_type="",
            trigger_name="",
            related_edges=_edge("anchor"),
            sequence=4,
        ),
    ]


@pytest.mark.asyncio
async def test_extract_encounter_skips_analysis_when_trigger_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = WorkflowEngine()
    executed_subgraphs: list[str] = []

    async def _resolve_action_chain(_event: WorkflowEvent):
        return _plan_actions()

    async def _execute_step(action: ActionDefinition, _state: dict):
        executed_subgraphs.append(action.subgraph_id)
        if action.subgraph_id == "extraction":
            return StepResult(
                action_id=action.action_id,
                subgraph_id=action.subgraph_id,
                status="completed",
                output={"entities": [{"text": "x"}]},
            )
        return StepResult(
            action_id=action.action_id,
            subgraph_id=action.subgraph_id,
            status="completed",
            output={},
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
            context={"mode": "extract_encounter", "trigger_analysis": False},
        )
    )

    assert result["status"] == "completed"
    assert executed_subgraphs == ["extraction", "persist"]
    assert [step["action_id"] for step in result["steps"]] == [
        "start",
        "extract",
        "persist",
        "anchor",
        "episode",
    ]


@pytest.mark.asyncio
async def test_extract_encounter_runs_analysis_when_trigger_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = WorkflowEngine()
    executed_subgraphs: list[str] = []

    async def _resolve_action_chain(_event: WorkflowEvent):
        return _plan_actions()

    async def _execute_step(action: ActionDefinition, _state: dict):
        executed_subgraphs.append(action.subgraph_id)
        output = {"entities": [{"text": "x"}]} if action.subgraph_id == "extraction" else {}
        return StepResult(
            action_id=action.action_id,
            subgraph_id=action.subgraph_id,
            status="completed",
            output=output,
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
            context={"mode": "extract_encounter", "trigger_analysis": True},
        )
    )

    assert result["status"] == "completed"
    assert executed_subgraphs == [
        "extraction",
        "persist",
        "anchor_detect",
        "episode_build",
    ]
