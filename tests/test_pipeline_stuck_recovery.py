"""Stuck-run recovery for zero-stage PipelineRuns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.workflow.durable_steps import StepRequest
from libs.workflow.pipeline_outbox import (
    build_first_step_message_id,
    build_first_step_recovery_message_id,
)
from libs.workflow.pipeline_stage_store import PipelineStageStore
from libs.workflow.pipeline_stuck_recovery import recover_stuck_pipeline_run
from tests.helpers.claim_race_client import InMemoryClaimClient


def _seed_run(client: InMemoryClaimClient, run_id: str) -> None:
    store = PipelineStageStore(client)
    store.upsert_run(
        StepRequest(
            event_type="referral_received",
            run_id=run_id,
            workflow_id="pd-referral-assessment",
            plan_definition_id="pd-referral-assessment",
            step_id="",
            patient_id="p1",
            encounter_id="e1",
            context={"case_id": "c1"},
        ),
        status="running",
    )


@pytest.mark.asyncio
async def test_zero_stage_recovery_skips_when_recently_enqueued() -> None:
    client = InMemoryClaimClient()
    run_id = "run-stuck-1"
    _seed_run(client, run_id)
    client.runs[run_id]["first_step_enqueued"] = True
    client.runs[run_id]["updated_at"] = datetime.now(timezone.utc)

    bus = AsyncMock()
    with patch.dict("os.environ", {"STUCK_ZERO_STAGE_RETRY_SECONDS": "60"}):
        sent = await recover_stuck_pipeline_run(client, bus, run_id)
    assert sent == 0
    bus.send.assert_not_called()


@pytest.mark.asyncio
async def test_zero_stage_recovery_republishes_with_fresh_message_id() -> None:
    client = InMemoryClaimClient()
    run_id = "run-stuck-2"
    _seed_run(client, run_id)
    client.runs[run_id]["first_step_enqueued"] = True
    client.runs[run_id]["updated_at"] = datetime.now(timezone.utc) - timedelta(
        seconds=120
    )

    manifest = MagicMock()
    trigger = MagicMock()
    trigger.trigger_name = "referral-received"
    trigger.node_type = "trigger"
    trigger.action_id = "act-ref-durable-start"
    extract = MagicMock()
    extract.action_id = "act-ref-extract"
    extract.trigger_name = ""
    extract.node_type = "action"
    extract.related_edges = [
        {
            "actionId": "act-ref-durable-start",
            "sourceHandle": "next",
            "targetHandle": "prev",
        }
    ]
    extract.related_actions = [
        {"actionId": "act-ref-durable-start", "relationship": "after-end"}
    ]
    manifest.actions = [trigger, extract]

    bus = AsyncMock()
    with (
        patch.dict("os.environ", {"STUCK_ZERO_STAGE_RETRY_SECONDS": "60"}),
        patch(
            "libs.workflow.pipeline_stuck_recovery.load_plan_manifest",
            return_value=manifest,
        ),
    ):
        sent = await recover_stuck_pipeline_run(client, bus, run_id)

    assert sent == 1
    bus.send.assert_called_once()
    message = bus.send.call_args[0][1]
    assert message.message_id == build_first_step_recovery_message_id(
        run_id, "act-ref-extract", 1
    )
    assert message.message_id != build_first_step_message_id(run_id, "act-ref-extract")
