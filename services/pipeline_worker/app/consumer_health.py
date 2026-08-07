"""Service Bus consumer health state for pipeline-worker /health/consumer.

Atlas trace:
  DO: DO-C2F6CA16
  DI: DI-06CB6881
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C2F6CA16")
"""

from __future__ import annotations

from typing import Any

_consumer_state: dict[str, Any] = {
    "queue": "",
    "running": False,
    "subscribed": False,
    "started_at": None,
    "last_heartbeat_at": None,
    "last_message_at": None,
    "last_error": None,
    "listener": {},
}
_message_bus: Any = None


def init_consumer_state(queue_name: str) -> None:
    _consumer_state["queue"] = queue_name


def set_message_bus(bus: Any) -> None:
    global _message_bus
    _message_bus = bus


def clear_message_bus() -> None:
    global _message_bus
    _message_bus = None


def consumer_state() -> dict[str, Any]:
    return _consumer_state


def consumer_health_payload() -> dict[str, Any]:
    bus = _message_bus
    queue = str(_consumer_state.get("queue") or "")
    if bus is not None and hasattr(bus, "listener_health") and queue:
        _consumer_state["listener"] = bus.listener_health(queue)
    listener = _consumer_state.get("listener") or {}
    listener_alive = listener.get("listener_alive")
    unhealthy_reasons: list[str] = []
    if not _consumer_state.get("running"):
        unhealthy_reasons.append("consumer_not_running")
    if not _consumer_state.get("subscribed"):
        unhealthy_reasons.append("not_subscribed")
    if _consumer_state.get("last_error"):
        unhealthy_reasons.append("last_error")
    if listener_alive is False:
        unhealthy_reasons.append("listener_task_dead")
    healthy = not unhealthy_reasons
    return {
        "healthy": healthy,
        "unhealthy_reasons": unhealthy_reasons,
        **_consumer_state,
    }
