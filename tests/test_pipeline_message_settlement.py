"""Settlement policy tests for durable pipeline Service Bus handlers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from libs.message_bus.settlement import (
    MessageDeferError,
    enforce_durable_step_settlement,
    resolve_durable_step_settlement,
    validate_pipeline_lease_config,
)
from libs.workflow.durable_steps import StepResult
from libs.workflow.stage_lease import StageLeaseBusyError
from services.pipeline_worker.app.services.durable_dispatcher import (
    handle_durable_message,
)


class _NoopBus:
    async def send(self, *_args, **_kwargs) -> None:
        return None

    async def close(self) -> None:
        return None


def test_resolve_durable_step_settlement_completed_and_poisoned() -> None:
    assert resolve_durable_step_settlement(StepResult(status="completed")) == "complete"
    assert (
        resolve_durable_step_settlement(
            StepResult(status="completed", warnings=["already_completed"])
        )
        == "complete"
    )
    assert resolve_durable_step_settlement(StepResult(status="poisoned")) == "complete"


def test_resolve_durable_step_settlement_skipped_abandons() -> None:
    assert (
        resolve_durable_step_settlement(
            StepResult(status="skipped", warnings=["stale_lease"])
        )
        == "abandon"
    )


def test_enforce_durable_step_settlement_raises_on_skipped() -> None:
    with pytest.raises(MessageDeferError, match="stale_lease"):
        enforce_durable_step_settlement(
            StepResult(status="skipped", warnings=["stale_lease"]),
            message_id="msg-1",
            run_id="run-1",
            action_id="act-1",
        )


@pytest.mark.asyncio
async def test_message_defer_error_is_abandon_not_failure() -> None:
    """Defer errors are not generic handler failures (settlement policy)."""
    defer = StageLeaseBusyError("stage busy", action_id="act-1", run_id="run-1")
    assert isinstance(defer, MessageDeferError)
    assert defer.reason == "stage_lease_busy"


@pytest.mark.asyncio
async def test_handle_durable_message_busy_propagates_defer() -> None:
    bus = _NoopBus()
    body = {
        "event_type": "durable_step",
        "action_id": "act-ref-extract",
        "step_id": "act-ref-extract",
        "plan_definition_id": "pd-referral-assessment",
        "run_id": "run-busy-dispatch",
        "patient_id": "p-busy",
        "_message_id": "msg-busy-dispatch",
    }

    async def _run_step(*_args, **_kwargs):
        raise StageLeaseBusyError(
            "stage busy",
            action_id="act-ref-extract",
            run_id="run-busy-dispatch",
        )

    with patch(
        "libs.workflow.durable_step_runner.DurableStepRunner.run_step",
        side_effect=_run_step,
    ):
        with pytest.raises(StageLeaseBusyError):
            await handle_durable_message(body, bus=bus)


def test_validate_pipeline_lease_config_flags_dangerous_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIPELINE_STAGE_LEASE_SECONDS", "120")
    monkeypatch.setenv("PIPELINE_STAGE_HEARTBEAT_SECONDS", "120")
    monkeypatch.setenv("SB_MAX_LOCK_RENEWAL_SECONDS", "60")
    monkeypatch.setenv("SB_MAX_CONCURRENT_CALLS", "64")
    warnings = validate_pipeline_lease_config()
    assert any("HEARTBEAT" in item for item in warnings)
    assert any("SB_MAX_LOCK_RENEWAL" in item for item in warnings)
    assert any("SB_MAX_CONCURRENT" in item for item in warnings)
    assert any("PIPELINE_STAGE_LEASE_SECONDS" in item for item in warnings)
