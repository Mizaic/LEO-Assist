"""Versioned trace events for Validation Lab run inspector (Redis SSE).

Atlas trace:
  DO: DO-158BE606
  DI: DI-FE423B8D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

TRACE_SCHEMA_VERSION = "1"
_MAX_KEY_LIST = max(8, int(os.getenv("LAB_TRACE_MAX_KEYS", "24")))
_PINNED_KEYS = (
    "form_schema_fingerprint",
    "form_schema_match",
    "form_schema_label",
)


def _top_level_keys(state: Any) -> list[str]:
    if not isinstance(state, dict):
        return []
    all_keys = {str(k) for k in state.keys()}
    pinned = [k for k in _PINNED_KEYS if k in all_keys]
    rest = sorted(all_keys - set(pinned))
    room = max(0, _MAX_KEY_LIST - len(pinned))
    return sorted(pinned + rest[:room])


def build_trace_event(
    event_type: str,
    run_id: str,
    *,
    service: str = "pipeline-worker",
    action_id: str = "",
    step_id: str = "",
    status: str = "",
    duration_ms: int | None = None,
    input_keys: list[str] | None = None,
    output_keys: list[str] | None = None,
    subgraph_id: str = "",
    worker_id: str = "",
    error: str = "",
    patient_id: str = "",
    plan_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalised trace payload for Redis SSE consumers."""
    payload: dict[str, Any] = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "type": event_type,
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "service": service,
    }
    if action_id:
        payload["action_id"] = action_id
    if step_id:
        payload["step_id"] = step_id
    if status:
        payload["status"] = status
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    if input_keys:
        payload["input_keys"] = list(input_keys)[:_MAX_KEY_LIST]
    if output_keys:
        payload["output_keys"] = list(output_keys)[:_MAX_KEY_LIST]
    if subgraph_id:
        payload["subgraph_id"] = subgraph_id
    if worker_id:
        payload["worker_id"] = worker_id
    if error:
        payload["error"] = error[:500]
    if patient_id:
        payload["patient_id"] = patient_id
    if plan_id:
        payload["plan_id"] = plan_id
    if extra:
        for key, value in extra.items():
            if key not in payload and value is not None:
                payload[key] = value
    return payload


def publish_run_trace(run_id: str, event: dict[str, Any]) -> None:
    """Publish a trace event via the shared Redis progress channel."""
    if not run_id:
        return
    try:
        from services.coding_worker.app.services.progress_publisher import (
            publish_progress,
        )

        publish_progress(run_id, event)
    except Exception:
        return


def keys_from_state(state: Any) -> list[str]:
    """Return top-level pipeline state keys safe for SSE (no clinical text)."""
    return _top_level_keys(state)
