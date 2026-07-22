"""Verify the pub/sub contract for pd-referral-assessment via DurableStepRunner.

Replaces the deleted referral_durable_steps module tests (G5.1).

Atlas trace:
  DO: DO-CE65B1F2
  DI: DI-36F80B95
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.message_bus.base import Message
from libs.workflow.durable_step_runner import (
    DURABLE_STEP_EVENT,
    DurableStepRunner,
    _Action,
)
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.pipeline_stage_store import StageClaimResult, StageCompleteResult

FAKE_CONTEXT = {
    "source": "ai_summarisation_scenario",
    "case_id": "upper_gi_form_001",
    "parent_run_id": "parent-run-123",
}


def _manifest(*actions: _Action) -> PlanManifest:
    return PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=1,
        version_node_id="ver-test-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=tuple(actions),
    )


def _terminal_action() -> _Action:
    return _Action(
        action_id="act-ref-sbar",
        subgraph_id="sbar",
        completion_queue="referral-assessments-output",
        completion_event_type="referral_assessment_completed",
    )


@pytest.mark.asyncio
async def test_terminal_sbar_publishes_completion_to_output_queue() -> None:
    mock_bus = AsyncMock()
    mock_bus.send = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.invoke = MagicMock(return_value={"sbar_assessment_id": "assess-xyz"})

    body = {
        "event_type": DURABLE_STEP_EVENT,
        "action_id": "act-ref-sbar",
        "step_id": "act-ref-sbar",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-pubsub-1",
        "patient_id": "patient-1",
        "guideline_id": "NG12",
        "completeness_domain": "cancer_referrals",
        "completeness_subdomain": "upper_gi",
        "context": FAKE_CONTEXT,
        "_message_id": "msg-terminal-1",
    }

    store = MagicMock(
        ensure_schema=MagicMock(),
        upsert_run=MagicMock(),
        claim_stage=MagicMock(
            return_value=StageClaimResult(
                outcome="claimed",
                lease_owner="worker-1",
                lease_generation=1,
            )
        ),
        complete_stage=MagicMock(return_value=StageCompleteResult(outcome="completed")),
        mark_next_published=MagicMock(),
        renew_stage_lease=MagicMock(return_value=True),
    )

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(_terminal_action()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PatientGraphClient",
            return_value=MagicMock(close=MagicMock()),
        ),
        patch(
            "libs.workflow.durable_step_runner.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "patient-1", **FAKE_CONTEXT},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):
        await DurableStepRunner.run_step(body, bus=mock_bus)

    mock_bus.send.assert_called_once()
    queue, msg = mock_bus.send.call_args.args
    assert queue == "referral-assessments-output"
    assert isinstance(msg, Message)
    assert msg.body["event_type"] == "referral_assessment_completed"
    assert msg.body["sbar_assessment_id"] == "assess-xyz"
    assert msg.body["context"]["case_id"] == "upper_gi_form_001"


@pytest.mark.asyncio
async def test_internal_step_publishes_next_durable_step_to_pipeline_queue() -> None:
    current = _Action(action_id="act-ref-extract", subgraph_id="extraction")
    nxt = _Action(
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
        "run_id": "run-pubsub-2",
        "patient_id": "patient-1",
        "context": FAKE_CONTEXT,
        "_message_id": "msg-internal-1",
    }

    with (
        patch(
            "libs.workflow.durable_step_runner.load_manifest_for_run",
            return_value=_manifest(current, nxt),
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
                claim_stage=MagicMock(
                    return_value=StageClaimResult(
                        outcome="claimed",
                        lease_owner="worker-1",
                        lease_generation=1,
                    )
                ),
                complete_stage=MagicMock(
                    return_value=StageCompleteResult(outcome="completed")
                ),
                mark_next_published=MagicMock(),
                renew_stage_lease=MagicMock(return_value=True),
            ),
        ),
        patch(
            "libs.workflow.durable_step_runner.dispatch_stage_outbox",
            new_callable=AsyncMock,
        ) as dispatch_mock,
        patch(
            "libs.workflow.durable_step_runner.load_step_state",
            return_value={"patient_id": "patient-1"},
        ),
        patch(
            "libs.pipeline_graph.registry.get_registry",
            return_value=MagicMock(build=MagicMock(return_value=mock_graph)),
        ),
    ):

        async def _dispatch(_store, bus, _request):
            await bus.send(
                "pipeline-jobs",
                Message(
                    body={
                        "event_type": DURABLE_STEP_EVENT,
                        "action_id": "act-ref-post-process",
                        "run_id": "run-pubsub-2",
                        "patient_id": "patient-1",
                    }
                ),
            )
            return 1

        dispatch_mock.side_effect = _dispatch
        await DurableStepRunner.run_step(body, bus=mock_bus)

    queue, msg = mock_bus.send.call_args.args
    assert queue == "pipeline-jobs"
    assert msg.body["event_type"] == DURABLE_STEP_EVENT
    assert msg.body["action_id"] == "act-ref-post-process"
