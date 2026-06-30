"""Unit tests for libs/workflow/durable_step_runner.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    DurableStepRunner,
    _Action,
    _build_outgoing_edges,
    _evaluate_condition_port,
    _resolve_next_action_ids,
    is_durable_runner_enabled,
)
from libs.workflow.durable_steps import StepResult as DurableStepResult


# ---------------------------------------------------------------------------
# is_durable_runner_enabled
# ---------------------------------------------------------------------------


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DURABLE_ENGINE_ENABLED", raising=False)
    assert is_durable_runner_enabled("pd-referral-assessment") is False


def test_referral_flag_enables_referral_only(monkeypatch):
    monkeypatch.setenv("DURABLE_ENGINE_ENABLED", "referral")
    assert is_durable_runner_enabled("pd-referral-assessment") is True
    assert is_durable_runner_enabled("pd-gp-encounter-coding") is False


def test_true_flag_enables_all(monkeypatch):
    monkeypatch.setenv("DURABLE_ENGINE_ENABLED", "true")
    assert is_durable_runner_enabled("pd-referral-assessment") is True
    assert is_durable_runner_enabled("pd-gp-encounter-coding") is True


# ---------------------------------------------------------------------------
# _build_outgoing_edges
# ---------------------------------------------------------------------------


def _make_action(action_id, related_actions=None, related_edges=None):
    return _Action(
        action_id=action_id,
        subgraph_id="extraction",
        related_actions=related_actions or [],
        related_edges=related_edges or [],
    )


def test_build_outgoing_from_related_actions():
    a = _make_action("act-a")
    b = _make_action("act-b", related_actions=[{"actionId": "act-a"}])
    outgoing = _build_outgoing_edges([a, b])
    assert "act-a" in outgoing
    assert outgoing["act-a"][0]["target"] == "act-b"


def test_build_outgoing_deduplicates():
    b = _make_action(
        "act-b",
        related_actions=[{"actionId": "act-a"}],
        related_edges=[{"actionId": "act-a"}],
    )
    outgoing = _build_outgoing_edges([_make_action("act-a"), b])
    assert len(outgoing["act-a"]) == 1


# ---------------------------------------------------------------------------
# _evaluate_condition_port
# ---------------------------------------------------------------------------


def test_condition_matches_rule():
    action = _Action(
        action_id="act-cond",
        subgraph_id="condition",
        node_type="condition",
        config={
            "params": {
                "rules": [
                    {
                        "field": "extraction_failed",
                        "operator": "==",
                        "value": "true",
                        "outputPort": "failed",
                    }
                ],
                "defaultPort": "ok",
            }
        },
    )
    assert _evaluate_condition_port(action, {"extraction_failed": "true"}) == "failed"
    assert _evaluate_condition_port(action, {"extraction_failed": "false"}) == "ok"


# ---------------------------------------------------------------------------
# _resolve_next_action_ids
# ---------------------------------------------------------------------------


def test_resolve_next_plain_action():
    action = _make_action("act-a")
    b = _make_action("act-b", related_actions=[{"actionId": "act-a"}])
    outgoing = _build_outgoing_edges([action, b])
    result = DurableStepResult(status="completed")
    next_ids = _resolve_next_action_ids(action, result, outgoing)
    assert next_ids == ["act-b"]


def test_resolve_next_condition_takes_default():
    cond = _Action(
        action_id="act-cond",
        subgraph_id="condition",
        node_type="condition",
    )
    ok_action = _Action(
        action_id="act-ok",
        subgraph_id="post_processing",
        related_edges=[
            {"actionId": "act-cond", "sourceHandle": "ok", "targetHandle": None}
        ],
    )
    fail_action = _Action(
        action_id="act-fail",
        subgraph_id="notify",
        related_edges=[
            {"actionId": "act-cond", "sourceHandle": "else", "targetHandle": None}
        ],
    )
    outgoing = _build_outgoing_edges([cond, ok_action, fail_action])
    result = DurableStepResult(
        status="completed", output={"condition_port": "else"}
    )
    next_ids = _resolve_next_action_ids(cond, result, outgoing)
    assert next_ids == ["act-fail"]


# ---------------------------------------------------------------------------
# DurableStepRunner.start (mocked Neo4j + bus)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_publishes_first_action():
    trigger_action = _Action(
        action_id="act-trigger",
        subgraph_id="trigger",
        node_type="trigger",
        trigger_name="referral-received",
    )
    first_action = _Action(
        action_id="act-ref-extract",
        subgraph_id="extraction",
        related_actions=[{"actionId": "act-trigger"}],
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()

    body = {
        "event_type": "referral-received",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-001",
        "patient_id": "p-001",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner._load_all_actions",
            return_value=[trigger_action, first_action],
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
                close=MagicMock(),
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                upsert_run=MagicMock(),
            ),
        ),
    ):
        await DurableStepRunner.start(body, bus=mock_bus)

    mock_bus.send.assert_called_once()
    sent_body = mock_bus.send.call_args[0][1].body
    assert sent_body["action_id"] == "act-ref-extract"
    assert sent_body["event_type"] == DURABLE_STEP_EVENT


# ---------------------------------------------------------------------------
# DurableStepRunner.run_step (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_step_invokes_subgraph_and_publishes_next():
    current_action = _Action(
        action_id="act-ref-extract",
        subgraph_id="extraction",
    )
    next_action = _Action(
        action_id="act-ref-post-process",
        subgraph_id="post_processing",
        related_actions=[{"actionId": "act-ref-extract"}],
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"entities": []})

    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-002",
        "patient_id": "p-002",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner._load_all_actions",
            return_value=[current_action, next_action],
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                upsert_run=MagicMock(),
                start_stage=MagicMock(),
                complete_stage=MagicMock(),
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-002", "entities": []},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    mock_bus.send.assert_called_once()
    sent_body = mock_bus.send.call_args[0][1].body
    assert sent_body["action_id"] == "act-ref-post-process"


@pytest.mark.asyncio
async def test_run_step_terminal_publishes_completion():
    terminal_action = _Action(
        action_id="act-ref-sbar",
        subgraph_id="sbar",
        completion_queue="referral-assessments-output",
        completion_event_type="referral_assessment_completed",
    )

    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"sbar_assessment_id": "assess-1"})

    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-sbar",
        "step_id": "act-ref-sbar",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-003",
        "patient_id": "p-003",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner._load_all_actions",
            return_value=[terminal_action],
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=MagicMock(
                ensure_schema=MagicMock(),
                upsert_run=MagicMock(),
                start_stage=MagicMock(),
                complete_stage=MagicMock(),
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "p-003"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        result = await DurableStepRunner.run_step(body, bus=mock_bus)

    assert result.status == "completed"
    mock_bus.send.assert_called_once()
    sent_body = mock_bus.send.call_args[0][1].body
    assert sent_body["event_type"] == "referral_assessment_completed"
