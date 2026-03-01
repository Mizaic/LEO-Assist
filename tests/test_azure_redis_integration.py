"""Integration test for Azure Redis-backed auth sessions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def test_azure_redis_session_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify session save/load/delete works against Azure Redis."""
    load_dotenv(ROOT / "secrets" / ".env")
    conn = os.getenv("AZURE_REDIS_CONNECTION_STRING")
    if not conn:
        pytest.skip("AZURE_REDIS_CONNECTION_STRING is not set")

    try:
        import redis  # noqa: F401
    except ModuleNotFoundError as exc:
        pytest.fail(f"Python package 'redis' is required for this integration test: {exc}")

    from app.services import session_store

    # Force session_store to use Azure connection string path for this test.
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("AZURE_REDIS_CONNECTION_STRING", conn)
    monkeypatch.delenv("DISABLE_REDIS", raising=False)

    session_store._redis_client = None
    with session_store._memory_store_lock:
        session_store._memory_store.clear()

    client = session_store._get_redis()
    assert client is not None, "Failed to connect to Azure Redis"

    session_id = session_store.create_session_id()
    payload = {"email": "integration@test.local", "access_token": "token-for-test"}
    key = f"{session_store.SESSION_PREFIX}{session_id}"

    try:
        session_store.save_session(session_id, payload)

        # Assert value exists in Redis (not just in-memory fallback).
        raw = client.get(key)
        assert raw is not None, "Session key was not written to Redis"

        loaded = session_store.load_session(session_id)
        assert loaded is not None
        assert loaded["email"] == payload["email"]
        assert loaded["access_token"] == payload["access_token"]

        session_store.delete_session(session_id)
        assert client.get(key) is None
    finally:
        # Cleanup in case test fails mid-way.
        try:
            client.delete(key)
        except Exception:
            pass
