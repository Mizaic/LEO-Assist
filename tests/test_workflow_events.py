from __future__ import annotations

import pytest

from libs.message_bus.base import Message
from libs.workflow.events import ServiceBusEventHandler


class _EngineStub:
    def __init__(self) -> None:
        self.last_event = None

    async def handle_event(self, event, step_callback=None):
        self.last_event = event
        _ = step_callback
        return {"status": "ok", "run_id": event.run_id}


@pytest.mark.asyncio
async def test_service_bus_handler_uses_correlation_id_as_run_id():
    engine = _EngineStub()
    handler = ServiceBusEventHandler(engine)  # type: ignore[arg-type]
    msg = Message(
        body={
            "event_type": "encounter-created",
            "patient_id": "p-1",
            "plan_definition_id": "pd-1",
            "context": {"mode": "all"},
        },
        correlation_id="run-123",
    )

    out = await handler.handle_message(msg)
    assert out["status"] == "ok"
    assert engine.last_event is not None
    assert engine.last_event.run_id == "run-123"
