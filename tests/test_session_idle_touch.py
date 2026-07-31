"""VT-AA19233B -- session idle slide on activity.

Covers DI-8A96990F / DO-F7C82FB5:
  - idle timeout 0 disables idle expiry
  - idle timeout > 0 deletes after the window
  - authenticated API deps call touch_session
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


@pytest.fixture()
def session_store(monkeypatch: pytest.MonkeyPatch):
    from app.services import session_store as store

    store._redis_client = None
    monkeypatch.setenv("DISABLE_REDIS", "true")
    # Force in-memory path via stubbing redis ops on a fake client.
    mem: dict[str, str] = {}

    class _FakeRedis:
        def setex(self, key: str, ttl: int, value: str) -> bool:
            mem[key] = value
            return True

        def get(self, key: str) -> str | None:
            return mem.get(key)

        def delete(self, key: str) -> int:
            return 1 if mem.pop(key, None) is not None else 0

        def ping(self) -> bool:
            return True

    fake = _FakeRedis()
    monkeypatch.setattr(store, "_get_redis", lambda: fake)
    monkeypatch.setattr(store, "_redis_op", lambda fn, *a, **k: fn(*a, **k))
    monkeypatch.delenv("DISABLE_REDIS", raising=False)
    yield store
    store._redis_client = None


def test_touch_idle_zero_never_expires(session_store) -> None:
    """TC: When idle timeout minutes is zero, touch_session does not delete."""
    sid = session_store.create_session_id()
    session_store.save_session(
        sid,
        {
            "email": "user@example.com",
            "last_activity": time.time() - 3600,
            "session_ttl_seconds": 3600,
        },
        ttl_seconds=3600,
    )
    refreshed = session_store.touch_session(sid, idle_timeout_minutes=0)
    assert refreshed is not None
    assert refreshed["email"] == "user@example.com"
    assert refreshed["last_activity"] > time.time() - 5


def test_touch_expires_after_idle_window(session_store) -> None:
    """TC: Idle timeout > 0 deletes when last activity is older than window."""
    sid = session_store.create_session_id()
    session_store.save_session(
        sid,
        {
            "email": "user@example.com",
            "last_activity": time.time() - 31 * 60,
            "session_ttl_seconds": 3600,
        },
        ttl_seconds=3600,
    )
    assert session_store.touch_session(sid, idle_timeout_minutes=30) is None
    assert session_store.load_session(sid) is None


def test_touch_slides_within_idle_window(session_store) -> None:
    """TC: API activity within idle window updates last-activity."""
    sid = session_store.create_session_id()
    old = time.time() - 60
    session_store.save_session(
        sid,
        {
            "email": "user@example.com",
            "last_activity": old,
            "idle_timeout_minutes": 30,
            "session_ttl_seconds": 3600,
        },
        ttl_seconds=3600,
    )
    refreshed = session_store.touch_session(sid, idle_timeout_minutes=30)
    assert refreshed is not None
    assert refreshed["last_activity"] > old


def test_get_session_data_calls_touch(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC: Authenticated API dep slides idle via touch_session."""
    from app import deps

    touched: dict[str, Any] = {}

    def _touch(sid: str, idle_timeout_minutes: int = 30):
        touched["sid"] = sid
        touched["idle"] = idle_timeout_minutes
        return {
            "email": "user@example.com",
            "idle_timeout_minutes": 30,
            "last_activity": time.time(),
        }

    monkeypatch.setattr(
        deps,
        "load_session",
        MagicMock(
            return_value={
                "email": "user@example.com",
                "idle_timeout_minutes": 30,
            }
        ),
    )
    monkeypatch.setattr(deps, "touch_session", _touch)

    data = deps.get_session_data(leo_session="sess-abc")
    assert data["email"] == "user@example.com"
    assert touched == {"sid": "sess-abc", "idle": 30}
