"""Heartbeat cadence and immediate renewal for durable stage leases."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from libs.workflow.durable_steps import StepRequest
from libs.workflow.stage_lease import (
    _heartbeat_interval_seconds,
    heartbeat_stage_lease,
)


def _request() -> StepRequest:
    return StepRequest(
        event_type="persist",
        run_id="run-heartbeat-1",
        workflow_id="pd-referral-assessment",
        step_id="act-ref-persist",
        patient_id="p-heartbeat-1",
        plan_definition_id="pd-referral-assessment",
    )


def test_heartbeat_interval_fits_inside_short_lease() -> None:
    assert _heartbeat_interval_seconds(60) == 20
    assert _heartbeat_interval_seconds(3600, interval_seconds=120) == 120


@pytest.mark.asyncio
async def test_heartbeat_renews_before_first_sleep() -> None:
    store = MagicMock()
    store.renew_stage_lease.return_value = True
    task = asyncio.create_task(
        heartbeat_stage_lease(
            store,
            _request(),
            lease_owner="Curie:msg-1",
            lease_generation=1,
            lease_seconds=60,
            interval_seconds=30,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    store.renew_stage_lease.assert_called()
    assert store.renew_stage_lease.call_count >= 1
