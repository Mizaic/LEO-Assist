"""Verify the pub/sub contract for every step in pd-referral-assessment.

Each durable step must:
  1. Publish the correct next event to ``pipeline-jobs`` (internal steps).
  2. The terminal step (sbar_requested) must publish
     ``referral_assessment_completed`` to ``referral-assessments-output``
     -- NOT to pipeline-jobs -- so downstream consumers receive a clean
     completion signal without access to the internal step queue.
  3. Context (including consumer correlation IDs such as ``case_id`` and
     ``source``) must pass through unchanged to the completion event.

Atlas trace:
  DO: DO-C2F6CA16  (referral_durable_steps)
  DI: DI-06CB6881
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_ROOT = Path(__file__).parent.parent / "services" / "pipeline_worker"
if str(_WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKER_ROOT))

from app.services.referral_durable_steps import (  # noqa: E402
    REFERRAL_OUTPUT_QUEUE,
    REFERRAL_STEPS,
    REFERRAL_STEP_BY_EVENT,
    REFERRAL_WORKFLOW_ID,
    _build_completion_body,
    _persist_completion_event,
    handle_referral_durable_message,
    start_referral_durable_workflow,
)
from libs.message_bus.base import Message  # noqa: E402
from libs.workflow.durable_steps import StepRequest, StepResult  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CONTEXT = {
    "source": "ai_summarisation_scenario",
    "case_id": "upper_gi_form_001",
    "parent_run_id": "parent-run-123",
}


def _request(event_type: str) -> StepRequest:
    defn = REFERRAL_STEP_BY_EVENT[event_type]
    return StepRequest(
        event_type=event_type,
        run_id="run-abc",
        workflow_id=REFERRAL_WORKFLOW_ID,
        step_id=defn.step_id,
        patient_id="patient-1",
        encounter_id="encounter-1",
        plan_definition_id=REFERRAL_WORKFLOW_ID,
        guideline_id="NG12",
        completeness_domain="cancer_referrals",
        completeness_subdomain="upper_gi",
        context=FAKE_CONTEXT,
    )


def _fake_store():
    store = MagicMock()
    store.ensure_schema = MagicMock()
    store.upsert_run = MagicMock()
    store.start_stage = MagicMock()
    store.complete_stage = MagicMock()
    store.load_accumulated_state = MagicMock(return_value={})
    return store


# ---------------------------------------------------------------------------
# Step chain integrity
# ---------------------------------------------------------------------------


def test_referral_steps_chain_is_complete():
    """Every internal next_event_type must map to a known step."""
    known = {s.event_type for s in REFERRAL_STEPS}
    for step in REFERRAL_STEPS:
        if step.next_event_type and step.next_step_id:
            assert step.next_event_type in known, (
                f"{step.step_id}: next_event_type '{step.next_event_type}' "
                f"has no matching step definition"
            )


def test_terminal_step_has_completion_event_type():
    """The last step must carry a completion_event_type and no next_step_id."""
    terminal = REFERRAL_STEPS[-1]
    assert terminal.next_event_type is None
    assert terminal.next_step_id is None
    assert terminal.completion_event_type == "referral_assessment_completed"


def test_no_human_review_step_in_workflow():
    """human_review_requested must not be inside the device workflow."""
    event_types = {s.event_type for s in REFERRAL_STEPS}
    assert "human_review_requested" not in event_types


# ---------------------------------------------------------------------------
# start_referral_durable_workflow publishes to pipeline-jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_publishes_extraction_requested_to_pipeline_queue():
    bus = AsyncMock()
    bus.send = AsyncMock()
    fake_client = MagicMock()
    fake_client.run = MagicMock(return_value=[])
    fake_client.close = MagicMock()

    with (
        patch(
            "app.services.referral_durable_steps.PatientGraphClient",
            return_value=fake_client,
        ),
        patch(
            "app.services.referral_durable_steps.PipelineStageStore",
            return_value=_fake_store(),
        ),
    ):
        await start_referral_durable_workflow(
            {
                "event_type": "referral-received",
                "plan_definition_id": REFERRAL_WORKFLOW_ID,
                "patient_id": "p1",
                "encounter_id": "e1",
                "guideline_id": "NG12",
                "context": FAKE_CONTEXT,
            },
            bus=bus,
        )

    assert bus.send.await_count == 1
    queue, msg = bus.send.await_args.args
    assert queue == "pipeline-jobs"
    assert isinstance(msg, Message)
    assert msg.body["event_type"] == "extraction_requested"
    assert msg.body["context"] == FAKE_CONTEXT


# ---------------------------------------------------------------------------
# Each internal step publishes the correct next event to pipeline-jobs
# ---------------------------------------------------------------------------

_INTERNAL_STEPS = [
    (s.event_type, s.next_event_type)
    for s in REFERRAL_STEPS
    if s.next_event_type and s.next_step_id
]


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type,expected_next", _INTERNAL_STEPS)
async def test_internal_step_publishes_to_pipeline_queue(
    event_type: str, expected_next: str
) -> None:
    bus = AsyncMock()
    bus.send = AsyncMock()
    fake_client = MagicMock()
    fake_client.run = MagicMock(return_value=[])
    fake_client.close = MagicMock()

    store = _fake_store()
    store.load_accumulated_state = MagicMock(return_value={"encounter_text": "text"})

    with (
        patch(
            "app.services.referral_durable_steps.PatientGraphClient",
            return_value=fake_client,
        ),
        patch(
            "app.services.referral_durable_steps.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "app.services.referral_durable_steps._run_definition",
            return_value=StepResult(
                status="completed",
                output={},
                next_event_type=expected_next,
                next_step_id=REFERRAL_STEP_BY_EVENT[expected_next].step_id,
            ),
        ),
    ):
        step_id = REFERRAL_STEP_BY_EVENT[event_type].step_id
        await handle_referral_durable_message(
            _request(event_type).to_message(event_type, step_id),
            bus=bus,
        )

    assert bus.send.await_count == 1
    queue, msg = bus.send.await_args.args
    assert queue == "pipeline-jobs", (
        f"{event_type}: expected pipeline-jobs, got {queue}"
    )
    assert msg.body["event_type"] == expected_next


# ---------------------------------------------------------------------------
# Terminal step publishes to the output queue, not pipeline-jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sbar_step_publishes_completion_to_output_queue():
    bus = AsyncMock()
    bus.send = AsyncMock()
    fake_client = MagicMock()
    fake_client.run = MagicMock(return_value=[])
    fake_client.close = MagicMock()

    store = _fake_store()
    store.load_accumulated_state = MagicMock(return_value={})

    with (
        patch(
            "app.services.referral_durable_steps.PatientGraphClient",
            return_value=fake_client,
        ),
        patch(
            "app.services.referral_durable_steps.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "app.services.referral_durable_steps._run_definition",
            return_value=StepResult(
                status="completed",
                output={"sbar_assessment_id": "assess-xyz"},
                next_event_type=None,
                next_step_id=None,
            ),
        ),
    ):
        await handle_referral_durable_message(
            _request("sbar_requested").to_message(
                "sbar_requested", "durable-ref-sbar"
            ),
            bus=bus,
        )

    assert bus.send.await_count == 1
    queue, msg = bus.send.await_args.args
    assert queue == REFERRAL_OUTPUT_QUEUE
    assert msg.body["event_type"] == "referral_assessment_completed"
    assert msg.body["assessment_id"] == "assess-xyz"
    assert msg.body["status"] == "completed"
    assert msg.body["context"]["case_id"] == "upper_gi_form_001"
    assert msg.body["context"]["source"] == "ai_summarisation_scenario"


@pytest.mark.asyncio
async def test_sbar_step_completion_status_completed_with_errors_on_partial():
    bus = AsyncMock()
    bus.send = AsyncMock()
    fake_client = MagicMock()
    fake_client.run = MagicMock(return_value=[])
    fake_client.close = MagicMock()

    with (
        patch(
            "app.services.referral_durable_steps.PatientGraphClient",
            return_value=fake_client,
        ),
        patch(
            "app.services.referral_durable_steps.PipelineStageStore",
            return_value=_fake_store(),
        ),
        patch(
            "app.services.referral_durable_steps._run_definition",
            return_value=StepResult(
                status="completed",
                output={"sbar_assessment_id": "assess-err"},
                errors=["background stage failed"],
                next_event_type=None,
                next_step_id=None,
            ),
        ),
    ):
        await handle_referral_durable_message(
            _request("sbar_requested").to_message(
                "sbar_requested", "durable-ref-sbar"
            ),
            bus=bus,
        )

    _, msg = bus.send.await_args.args
    assert msg.body["status"] == "completed_with_errors"
    assert "background stage failed" in msg.body["errors"]


# ---------------------------------------------------------------------------
# Completion body helper
# ---------------------------------------------------------------------------


def test_build_completion_body_passthrough():
    """Context fields survive into the completion event unchanged."""
    from app.services.referral_durable_steps import REFERRAL_STEP_BY_EVENT

    req = _request("sbar_requested")
    defn = REFERRAL_STEP_BY_EVENT["sbar_requested"]
    result = StepResult(
        status="completed",
        output={"sbar_assessment_id": "assess-1"},
        errors=[],
    )
    body = _build_completion_body(req, result, defn)

    assert body["event_type"] == "referral_assessment_completed"
    assert body["assessment_id"] == "assess-1"
    assert body["guideline_id"] == "NG12"
    assert body["completeness_domain"] == "cancer_referrals"
    assert body["completeness_subdomain"] == "upper_gi"
    assert body["context"]["case_id"] == "upper_gi_form_001"
    assert body["context"]["parent_run_id"] == "parent-run-123"
    assert body["status"] == "completed"


# ---------------------------------------------------------------------------
# _persist_completion_event writes completion_event_json to the graph
# ---------------------------------------------------------------------------


def test_persist_completion_event_writes_to_neo4j():
    """_persist_completion_event must call the Neo4j client with the correct
    query and parameters.  The JSON must be a serialised version of the body."""
    import json

    from libs.cypher.pipeline_stage_queries import WRITE_PIPELINE_RUN_COMPLETION

    fake_client = MagicMock()
    fake_client.run = MagicMock(return_value=[])
    fake_client.close = MagicMock()

    body = {"event_type": "referral_assessment_completed", "assessment_id": "a1"}
    with patch(
        "app.services.referral_durable_steps.PatientGraphClient",
        return_value=fake_client,
    ):
        _persist_completion_event("run-42", body)

    fake_client.run.assert_called_once_with(
        WRITE_PIPELINE_RUN_COMPLETION,
        run_id="run-42",
        completion_event_json=json.dumps(body, default=str),
    )
    fake_client.close.assert_called_once()


def test_persist_completion_event_is_best_effort():
    """A Neo4j failure must not raise -- just log a warning."""
    fake_client = MagicMock()
    fake_client.run = MagicMock(side_effect=RuntimeError("connection refused"))
    fake_client.close = MagicMock()

    with patch(
        "app.services.referral_durable_steps.PatientGraphClient",
        return_value=fake_client,
    ):
        # Should not raise
        _persist_completion_event("run-43", {"event_type": "test"})

    fake_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_sbar_step_writes_completion_event_to_graph():
    """The terminal step must persist the completion event to the graph
    immediately after publishing to the output queue."""
    bus = AsyncMock()
    bus.send = AsyncMock()
    fake_client = MagicMock()
    fake_client.run = MagicMock(return_value=[])
    fake_client.close = MagicMock()

    store = _fake_store()
    with (
        patch(
            "app.services.referral_durable_steps.PatientGraphClient",
            return_value=fake_client,
        ),
        patch(
            "app.services.referral_durable_steps.PipelineStageStore",
            return_value=store,
        ),
        patch(
            "app.services.referral_durable_steps._run_definition",
            return_value=StepResult(
                status="completed",
                output={"sbar_assessment_id": "assess-graph-1"},
                next_event_type=None,
                next_step_id=None,
            ),
        ),
    ):
        await handle_referral_durable_message(
            _request("sbar_requested").to_message(
                "sbar_requested", "durable-ref-sbar"
            ),
            bus=bus,
        )

    # PatientGraphClient.run must have been called at least twice:
    # once for PipelineStageStore internals and once for the completion write.
    # We look for the WRITE_PIPELINE_RUN_COMPLETION call specifically.
    from libs.cypher.pipeline_stage_queries import WRITE_PIPELINE_RUN_COMPLETION

    completion_calls = [
        call
        for call in fake_client.run.call_args_list
        if call.args and call.args[0] == WRITE_PIPELINE_RUN_COMPLETION
    ]
    assert len(completion_calls) == 1, (
        "WRITE_PIPELINE_RUN_COMPLETION was not called exactly once"
    )
    kwargs = completion_calls[0].kwargs
    assert kwargs["run_id"] is not None
    import json

    saved = json.loads(kwargs["completion_event_json"])
    assert saved["assessment_id"] == "assess-graph-1"
    assert saved["event_type"] == "referral_assessment_completed"
