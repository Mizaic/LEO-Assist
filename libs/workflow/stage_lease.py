"""Stage lease identity, heartbeat and typed defer outcomes.

Atlas trace:
  DI: DI-36F80B95
  DO: DO-CE65B1F2
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from libs.message_bus.settlement import MessageDeferError

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_SECONDS = max(
    15, int(os.getenv("PIPELINE_STAGE_HEARTBEAT_SECONDS", "120"))
)


class StageLeaseBusyError(MessageDeferError):
    """Another worker holds an unexpired lease; abandon the Service Bus message."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__("stage_lease_busy", detail=message, **context)


class StageLeaseStaleError(MessageDeferError):
    """Completion rejected because the stage lease was reclaimed."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__("stale_lease", detail=message, **context)


def _sanitize_worker_host(raw: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in "-_" else "-" for ch in (raw or "").strip()
    )
    return (cleaned or "worker")[:64]


def resolve_lease_owner(body: dict[str, Any]) -> str:
    """Stable worker identity for a single message delivery attempt.

    Prefers an explicit local agent name (PIPELINE_WORKER_NAME), then Azure
    Container Apps replica name, then hostname. Local multi-worker starts set
    PIPELINE_WORKER_NAME from a shared agent roster so Lab support context can
    tell Ada from Curie.
    """
    explicit = body.get("lease_owner") or body.get("_delivery_worker_id")
    if explicit:
        return str(explicit)
    host = _sanitize_worker_host(
        os.getenv("PIPELINE_WORKER_NAME")
        or os.getenv("CONTAINER_APP_REPLICA_NAME")
        or os.getenv("HOSTNAME")
        or os.getenv("COMPUTERNAME")
        or f"worker-{os.getpid()}"
    )
    msg_id = str(body.get("_message_id") or body.get("run_id") or uuid.uuid4())
    return f"{host}:{msg_id}"


def _heartbeat_interval_seconds(
    lease_seconds: int, interval_seconds: int | None = None
) -> int:
    """Pick a renewal cadence that always fits inside the lease window."""
    configured = interval_seconds or _DEFAULT_HEARTBEAT_SECONDS
    lease_cap = max(15, lease_seconds // 3)
    return min(configured, lease_cap)


async def heartbeat_stage_lease(
    store: Any,
    request: Any,
    *,
    lease_owner: str,
    lease_generation: int,
    lease_seconds: int,
    interval_seconds: int | None = None,
) -> None:
    """Renew the Neo4j stage lease until cancelled or renewal fails."""
    interval = _heartbeat_interval_seconds(lease_seconds, interval_seconds)
    while True:
        renewed = store.renew_stage_lease(
            request,
            lease_owner=lease_owner,
            lease_generation=lease_generation,
            lease_seconds=lease_seconds,
        )
        if not renewed:
            logger.warning(
                "Stage lease heartbeat stopped: run_id=%s step_id=%s owner=%s gen=%s",
                request.run_id,
                request.step_id,
                lease_owner,
                lease_generation,
            )
            return
        await asyncio.sleep(interval)
