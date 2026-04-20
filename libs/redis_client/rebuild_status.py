"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-412DE1A5
  DI: DI-B884A243
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-412DE1A5")
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libs.redis_client.checkpoint import CheckpointStore

_PREFIX = "rebuild_status:"
_TTL_SECONDS = 12 * 60 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(patient_id: str) -> str:
    return f"{_PREFIX}{patient_id}"


def begin_rebuild(patient_id: str, run_id: str, queued_jobs: int) -> None:
    store = CheckpointStore()
    store.set(
        _key(patient_id),
        {
            "patient_id": patient_id,
            "run_id": run_id,
            "status": "queued",
            "queued_jobs": int(max(queued_jobs, 0)),
            "updated_at": _now_iso(),
            "message": "Queued and waiting for worker pickup.",
        },
        ttl=_TTL_SECONDS,
    )


def get_rebuild_status(patient_id: str) -> dict[str, Any] | None:
    store = CheckpointStore()
    data = store.get(_key(patient_id))
    if not isinstance(data, dict):
        return None
    return data


def update_from_event(patient_id: str, run_id: str, event: dict[str, Any]) -> None:
    current = get_rebuild_status(patient_id)
    if not current:
        return
    if str(current.get("run_id") or "") != run_id:
        return

    ev_type = str(event.get("type") or "")
    status = str(current.get("status") or "queued")
    message = str(current.get("message") or "")
    if ev_type in {
        "step_completed",
        "run_started",
        "patient_started",
        "encounter_started",
    }:
        status = "running"
        step = str(event.get("subgraph_id") or "").strip()
        message = f"Running{f' ({step})' if step else ''}."
    elif ev_type in {"run_completed"}:
        status = "completed"
        message = "Rebuild completed."
    elif ev_type in {"run_error", "pipeline_error", "encounter_error"}:
        status = "failed"
        err = str(event.get("message") or event.get("error") or "").strip()
        message = f"Failed{f': {err}' if err else '.'}"

    store = CheckpointStore()
    next_value = {
        **current,
        "status": status,
        "message": message,
        "updated_at": _now_iso(),
    }
    store.set(_key(patient_id), next_value, ttl=_TTL_SECONDS)
