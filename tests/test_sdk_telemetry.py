"""LEO widget SDK telemetry verification tests.

Atlas trace:
  DI: DI-5F121122
  DO: DO-23DDE984
  VT: VT-7FF54A1B (POST /sdk/telemetry deduplicates by widget_instance_id + event_id)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).resolve().parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


class _FakeRedis:
    """Tiny in-memory stand-in for Azure Managed Redis (SET NX EX only).

    Models the only Redis surface sdk_telemetry depends on: SET NX EX.
    Real Redis returns True on first SET, None when the key already
    exists. We mirror that contract so the dedup branch is exercised.
    """

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float]] = {}

    def ping(self) -> bool:
        return True

    def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: int | None = None,
    ) -> Any:
        now = time.time()
        existing = self.store.get(key)
        if existing is not None and existing[1] > now:
            if nx:
                return None
        expires_at = now + (ex if ex is not None else 365 * 24 * 60 * 60)
        self.store[key] = (value, expires_at)
        return True


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.routers.sdk_telemetry import (
        _reset_telemetry_state_for_testing,
        router,
    )

    # Shared conftest points REDIS_URL at localhost. These tests prove
    # the in-process LRU, so they must not inherit a leftover Redis key
    # from an earlier run.
    monkeypatch.delenv("REDIS_URL", raising=False)
    _reset_telemetry_state_for_testing()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def redis_backed_client() -> TestClient:
    """Client wired to an in-memory Redis double (Azure managed Redis path)."""
    from app.routers.sdk_telemetry import (
        _reset_telemetry_state_for_testing,
        _set_redis_client_for_testing,
        router,
    )

    _reset_telemetry_state_for_testing()
    _set_redis_client_for_testing(_FakeRedis())
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _event(event_id: int = 1, **overrides) -> dict:
    base = {
        "widget_instance_id": "wi-test-001",
        "event_id": event_id,
        "type": "disclosure-opened",
        "assessment_id": "ASSESS-1",
        "emitted_at_ms": 1_700_000_000_000,
        "payload": {"stage": "background"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# VT-7FF54A1B - dedup by (widget_instance_id, event_id)
# ---------------------------------------------------------------------------


def test_first_post_returns_accepted(client: TestClient) -> None:
    response = client.post("/sdk/telemetry", json=_event())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["event_id"] == 1


def test_duplicate_post_returns_deduped(client: TestClient) -> None:
    response_a = client.post("/sdk/telemetry", json=_event())
    assert response_a.json()["status"] == "accepted"
    response_b = client.post("/sdk/telemetry", json=_event())
    assert response_b.status_code == 200
    assert response_b.json()["status"] == "deduped"


def test_different_event_id_is_not_deduped(client: TestClient) -> None:
    client.post("/sdk/telemetry", json=_event(event_id=1))
    second = client.post("/sdk/telemetry", json=_event(event_id=2))
    assert second.json()["status"] == "accepted"


def test_different_instance_id_is_not_deduped(client: TestClient) -> None:
    client.post("/sdk/telemetry", json=_event())
    second = client.post(
        "/sdk/telemetry",
        json=_event(widget_instance_id="wi-test-other"),
    )
    assert second.json()["status"] == "accepted"


def test_dedup_increments_counter_only_on_accepted(client: TestClient) -> None:
    from app.routers.sdk_telemetry import _telemetry_counter_for_testing

    client.post("/sdk/telemetry", json=_event(event_id=1))
    client.post("/sdk/telemetry", json=_event(event_id=1))
    client.post("/sdk/telemetry", json=_event(event_id=2))
    assert _telemetry_counter_for_testing() == 2


def test_invalid_event_type_is_rejected(client: TestClient) -> None:
    bad = _event()
    bad["type"] = "evil-event"
    response = client.post("/sdk/telemetry", json=bad)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# VT-7FF54A1B - dedup is multi-replica safe via Azure Managed Redis
# ---------------------------------------------------------------------------


def test_redis_backend_first_post_returns_accepted(
    redis_backed_client: TestClient,
) -> None:
    response = redis_backed_client.post("/sdk/telemetry", json=_event())
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_redis_backend_duplicate_post_returns_deduped(
    redis_backed_client: TestClient,
) -> None:
    redis_backed_client.post("/sdk/telemetry", json=_event())
    response = redis_backed_client.post("/sdk/telemetry", json=_event())
    assert response.status_code == 200
    assert response.json()["status"] == "deduped"


def test_redis_backend_dedups_across_simulated_replicas() -> None:
    """Two API replicas pointing at the same Redis must dedup, not double-count.

    Mounts two TestClients backed by independent FastAPI apps but
    the same _FakeRedis instance. Without shared Redis these would
    each accept the event (the in-process LRU is per-process); with
    Redis the second replica must report 'deduped'.
    """
    from app.routers.sdk_telemetry import (
        _reset_telemetry_state_for_testing,
        _set_redis_client_for_testing,
        router,
    )

    shared = _FakeRedis()
    _reset_telemetry_state_for_testing()
    _set_redis_client_for_testing(shared)
    app_a = FastAPI()
    app_a.include_router(router)
    client_a = TestClient(app_a)

    _reset_telemetry_state_for_testing()
    _set_redis_client_for_testing(shared)
    app_b = FastAPI()
    app_b.include_router(router)
    client_b = TestClient(app_b)

    response_a = client_a.post("/sdk/telemetry", json=_event())
    response_b = client_b.post("/sdk/telemetry", json=_event())

    assert response_a.json()["status"] == "accepted"
    assert response_b.json()["status"] == "deduped"


def test_redis_backend_falls_back_to_lru_when_set_raises() -> None:
    """If SET NX explodes the dedup contract still holds in-process."""
    from app.routers.sdk_telemetry import (
        _reset_telemetry_state_for_testing,
        _set_redis_client_for_testing,
        router,
    )

    class _FlakyRedis(_FakeRedis):
        def set(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("simulated redis outage")

    _reset_telemetry_state_for_testing()
    _set_redis_client_for_testing(_FlakyRedis())
    app = FastAPI()
    app.include_router(router)
    flaky_client = TestClient(app)

    first = flaky_client.post("/sdk/telemetry", json=_event())
    second = flaky_client.post("/sdk/telemetry", json=_event())

    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "deduped"
