"""VT-LEO-AI-194 -- POST /sbar/jobs publishes a dict-shaped Message.

Regression for the bytes-body bug (TypeError: Object of type bytes is
not JSON serializable). The Azure Service Bus and in-memory message
bus adapters expect ``Message.body`` to be a ``Dict[str, Any]`` and
serialise it themselves. The SBAR router previously
``json.dumps(...).encode("utf-8")``-d the payload before constructing
the Message, which caused the adapter's own ``json.dumps(message.body)``
call to raise ``TypeError: Object of type bytes is not JSON
serializable`` and surface as a 500 to the SBAR Playground.

These tests pin the contract:

  - ``Message.body`` is a plain dict;
  - the dict is round-trippable through ``json.dumps`` so the adapter
    can serialise it on the wire;
  - the dict carries the validated SBARRequestPayload fields
    (run_id, assessment_id, situation, background, ...).
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# services/api expects to be importable via the bare ``app`` package
# (e.g. ``from app.deps import require_admin``). Insert it on sys.path
# the same way ``test_work_queue.py`` does, and stub out the modules
# that would otherwise pull in Neo4j / cookie-store dependencies.
_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
sys.modules.setdefault(
    "app.db.neo4j_client",
    MagicMock(PatientGraphClient=MagicMock),
)
sys.modules.setdefault(
    "app.services.session_store",
    MagicMock(COOKIE_NAME="leo_session", load_session=MagicMock()),
)

from app.deps import require_admin  # noqa: E402
from libs.auth.org_scope import CallerScope, get_caller_scope  # noqa: E402
from libs.message_bus.base import Message  # noqa: E402
from app.routers import sbar as sbar_router_module  # noqa: E402
from app.routers.sbar import router as sbar_router  # noqa: E402


ADMIN_SCOPE = CallerScope(email="admin@example.test", is_admin=True)


def _make_app(monkeypatch) -> tuple[FastAPI, AsyncMock]:
    """Build a test app with the message-bus factory patched so we can
    inspect what the router sends without standing up Service Bus or
    Redis. The router imports ``create_message_bus`` lazily inside
    the request handler, so we patch the source module."""
    import libs.message_bus.factory as factory_module

    fake_bus = AsyncMock()
    fake_bus.send = AsyncMock()
    fake_bus.close = AsyncMock()
    monkeypatch.setattr(factory_module, "create_message_bus", lambda: fake_bus)

    app = FastAPI()
    app.include_router(sbar_router)
    app.dependency_overrides[get_caller_scope] = lambda: ADMIN_SCOPE
    app.dependency_overrides[require_admin] = lambda: None
    return app, fake_bus


def _minimal_body() -> dict[str, Any]:
    """Smallest valid SBARRequestPayload body the router accepts.

    Mirrors what the SBAR Playground POSTs: a PatientContext artifact
    plus one Encounter background source, no concern, no extra
    summarisation_context."""
    return {
        "run_id": str(uuid.uuid4()),
        "situation": {
            "patient_id": "pat-1",
            "artifacts": [
                {"type": "PatientContext", "id": "pat-1"},
            ],
        },
        "background": [
            {"type": "Encounter", "id": "enc-1"},
        ],
    }


def test_enqueue_publishes_message_with_dict_body_not_bytes(monkeypatch) -> None:
    app, fake_bus = _make_app(monkeypatch)
    response = TestClient(app).post("/sbar/jobs", json=_minimal_body())

    assert response.status_code == 200, response.text
    assert fake_bus.send.await_count == 1

    queue_name, message = fake_bus.send.await_args.args
    assert queue_name == "pipeline-jobs"
    assert isinstance(message, Message)
    assert isinstance(message.body, dict), (
        "Message.body must be a Dict[str, Any]; bytes triggers "
        "TypeError in the bus adapter's json.dumps call."
    )
    assert not isinstance(message.body, (bytes, bytearray, str))


def test_enqueue_message_body_is_json_serialisable(monkeypatch) -> None:
    app, fake_bus = _make_app(monkeypatch)
    TestClient(app).post("/sbar/jobs", json=_minimal_body())
    message = fake_bus.send.await_args.args[1]
    encoded = json.dumps(message.body)
    assert json.loads(encoded)["situation"]["patient_id"] == "pat-1"


def test_enqueue_message_body_round_trip_carries_run_id_and_assessment(
    monkeypatch,
) -> None:
    app, fake_bus = _make_app(monkeypatch)
    body = _minimal_body()
    response = TestClient(app).post("/sbar/jobs", json=body)
    out = response.json()

    message = fake_bus.send.await_args.args[1]
    assert message.body["run_id"] == out["run_id"]
    assert message.body["assessment_id"] == out["assessment_id"]
    assert message.body["event_type"] == "sbar_requested"
    assert message.body["situation"]["patient_id"] == "pat-1"
    assert message.subject == "sbar-requested"
    assert message.correlation_id == out["run_id"]
