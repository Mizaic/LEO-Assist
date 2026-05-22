"""Immutable audit log for terminology administrator actions.

Atlas trace:
  DO: DO-669D6A69 (Terminology administrator audit log)
  DI: DI-2AD4CCC3 (Maintain audit log of terminology administrator actions)
  VT: VT-CE12337D (Verify terminology administrator actions are recorded in audit log)

Every sync trigger, load completion, load failure, and configuration change
is appended here with user identity, timestamp, packages, action type, and
outcome. Entries are never mutated after writing (append-only list). Callers
read copies only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_LOCK = Lock()
_LOG: list[dict[str, Any]] = []

ACTION_SYNC_TRIGGER = "sync_trigger"
ACTION_SYNC_COMPLETE = "sync_complete"
ACTION_SYNC_ERROR = "sync_error"
ACTION_CONFIG_CHANGE = "config_change"

VALID_ACTIONS = frozenset(
    [ACTION_SYNC_TRIGGER, ACTION_SYNC_COMPLETE, ACTION_SYNC_ERROR, ACTION_CONFIG_CHANGE]
)


def write_entry(
    *,
    user: str,
    action_type: str,
    packages: list[str],
    outcome: str,
    detail: str = "",
) -> dict[str, Any]:
    """Append an immutable audit entry and return a copy of it."""
    if action_type not in VALID_ACTIONS:
        raise ValueError(f"Invalid action_type: {action_type!r}")
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "action_type": action_type,
        "packages": list(packages),
        "outcome": outcome,
        "detail": detail,
    }
    with _LOCK:
        _LOG.append(entry)
    return dict(entry)


def _copy_entry(e: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of entry with the packages list also copied."""
    result = dict(e)
    result["packages"] = list(e["packages"])
    return result


def get_entries(
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    """Return copies of audit entries, optionally filtered by ISO 8601 timestamp range."""
    with _LOCK:
        snapshot = list(_LOG)
    if since:
        snapshot = [e for e in snapshot if e["timestamp"] >= since]
    if until:
        snapshot = [e for e in snapshot if e["timestamp"] <= until]
    return [_copy_entry(e) for e in snapshot]


def run_sync_with_audit(
    user: str,
    packages: list[str],
    phases: set[int],
    events_queue: Any,
    full_sync_fn: Any,
    external_content: Any,
) -> None:
    """Run a TRUD full_sync and write audit entries on completion or error.

    Extracted here so it can be unit-tested without the FastAPI/app imports.
    The router's _run_sync_thread delegates to this function.
    """
    import logging

    logger = logging.getLogger(__name__)
    outcome = "success"
    detail = ""

    def emit(event: dict[str, Any]) -> None:
        events_queue.put(event)
        if event.get("type") == "sync_error":
            nonlocal outcome, detail
            outcome = "error"
            detail = event.get("msg", "")

    try:
        full_sync_fn(external_content, packages, phases, emit)
    except Exception as exc:
        logger.exception("Unexpected error in TRUD sync thread")
        outcome = "error"
        detail = str(exc)
        events_queue.put({"type": "sync_error", "msg": detail})
    finally:
        action = ACTION_SYNC_ERROR if outcome == "error" else ACTION_SYNC_COMPLETE
        try:
            write_entry(
                user=user,
                action_type=action,
                packages=packages,
                outcome=outcome,
                detail=detail,
            )
        except Exception:
            logger.warning("audit: failed to write sync completion entry", exc_info=True)
        events_queue.put(None)  # sentinel


def clear_for_testing() -> None:
    """Remove all entries. Only for use in tests."""
    with _LOCK:
        _LOG.clear()
