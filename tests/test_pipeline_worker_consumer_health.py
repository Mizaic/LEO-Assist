"""Pipeline worker Service Bus consumer health payload."""

from __future__ import annotations

from services.pipeline_worker.app.consumer_health import (
    consumer_health_payload,
    consumer_state,
    set_message_bus,
)


def test_consumer_health_unhealthy_when_listener_task_dead() -> None:
    consumer_state().update(
        {
            "queue": "pipeline-jobs",
            "running": True,
            "subscribed": True,
            "started_at": "t0",
            "last_heartbeat_at": "t1",
            "last_message_at": None,
            "last_error": None,
            "listener": {
                "listener_alive": False,
                "connect_count": 2,
                "last_connected_at": "t0",
            },
        }
    )

    class _Bus:
        def listener_health(self, _queue: str) -> dict:
            return consumer_state()["listener"]

    set_message_bus(_Bus())
    try:
        payload = consumer_health_payload()
    finally:
        set_message_bus(None)

    assert payload["healthy"] is False
    assert "listener_task_dead" in payload["unhealthy_reasons"]


def test_consumer_health_healthy_when_listener_alive() -> None:
    consumer_state().update(
        {
            "queue": "pipeline-jobs",
            "running": True,
            "subscribed": True,
            "started_at": "t0",
            "last_heartbeat_at": "t1",
            "last_message_at": "t2",
            "last_error": None,
            "listener": {
                "listener_alive": True,
                "connect_count": 1,
                "last_connected_at": "t0",
                "in_flight_handlers": 0,
            },
        }
    )

    class _Bus:
        def listener_health(self, _queue: str) -> dict:
            return consumer_state()["listener"]

    set_message_bus(_Bus())
    try:
        payload = consumer_health_payload()
    finally:
        set_message_bus(None)

    assert payload["healthy"] is True
    assert payload["unhealthy_reasons"] == []
