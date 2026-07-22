"""Service Bus message settlement policy for durable pipeline handlers.

Atlas trace:
  DI: DI-36F80B95
  DO: DO-CE65B1F2

Handlers signal deferral by raising MessageDeferError (or subclasses such as
StageLeaseBusyError). The Azure adapter abandons those messages so Service Bus
can redeliver after the Neo4j stage lease clears. Successful or idempotent
terminal outcomes complete the message.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

logger = logging.getLogger(__name__)

MessageSettlementAction = Literal["complete", "abandon"]


class MessageDeferError(Exception):
    """Handler asks the bus to abandon (defer) rather than complete."""

    def __init__(self, reason: str, **context: Any) -> None:
        self.reason = reason
        self.context = dict(context)
        super().__init__(reason)


def resolve_durable_step_settlement(result: Any) -> MessageSettlementAction:
    """Map a DurableStepResult to a Service Bus settlement action."""
    status = str(getattr(result, "status", "") or "")
    warnings = list(getattr(result, "warnings", []) or [])
    if status == "skipped":
        return "abandon"
    if status == "poisoned":
        return "complete"
    if status == "completed":
        return "complete"
    if status == "failed":
        return "abandon"
    return "complete"


def enforce_durable_step_settlement(
    result: Any,
    *,
    message_id: str = "",
    run_id: str = "",
    action_id: str = "",
) -> None:
    """Raise MessageDeferError when the step outcome must not complete the SB msg."""
    action = resolve_durable_step_settlement(result)
    if action == "abandon":
        warnings = list(getattr(result, "warnings", []) or [])
        reason = (
            "stale_lease"
            if "stale_lease" in warnings
            else str(getattr(result, "status", "") or "defer")
        )
        raise MessageDeferError(
            reason,
            message_id=message_id,
            run_id=run_id,
            action_id=action_id,
            warnings=warnings,
        )


def log_settlement_event(
    action: MessageSettlementAction,
    *,
    message_id: str,
    reason: str,
    **fields: Any,
) -> None:
    """Structured settlement log for lease outcomes and poison paths."""
    payload = {
        "settlement_action": action,
        "message_id": message_id,
        "reason": reason,
        **fields,
    }
    if action == "abandon":
        logger.info(
            "pipeline_message_defer message_id=%s reason=%s fields=%s",
            message_id,
            reason,
            payload,
        )
        return
    logger.info(
        "pipeline_message_complete message_id=%s reason=%s fields=%s",
        message_id,
        reason,
        payload,
    )


def validate_pipeline_lease_config() -> list[str]:
    """Return human-readable warnings for dangerous lease / bus settings."""
    lease = max(60, int(os.getenv("PIPELINE_STAGE_LEASE_SECONDS", "3600")))
    heartbeat = max(15, int(os.getenv("PIPELINE_STAGE_HEARTBEAT_SECONDS", "120")))
    lock_renewal = int(os.getenv("SB_MAX_LOCK_RENEWAL_SECONDS", "14400"))
    concurrent = max(1, int(os.getenv("SB_MAX_CONCURRENT_CALLS", "8")))
    warnings: list[str] = []
    if heartbeat >= lease:
        warnings.append(
            "PIPELINE_STAGE_HEARTBEAT_SECONDS must be less than "
            "PIPELINE_STAGE_LEASE_SECONDS or leases cannot renew in time"
        )
    if lock_renewal < lease:
        warnings.append(
            "SB_MAX_LOCK_RENEWAL_SECONDS is shorter than "
            "PIPELINE_STAGE_LEASE_SECONDS; Service Bus may redeliver mid-step"
        )
    if concurrent > 32:
        warnings.append(
            "SB_MAX_CONCURRENT_CALLS is very high; competing consumers may "
            "contend on stage leases and increase defer churn"
        )
    if lease < 300:
        warnings.append(
            "PIPELINE_STAGE_LEASE_SECONDS is under 300s; long LLM steps may "
            "lose the fence before heartbeat renewal"
        )
    return warnings
