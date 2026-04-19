"""Tests for the post-compile test-patient replay hook -- VT-LEO-AI-166.

Verifies that _trigger_test_patient_replay() in the terminology-api
guidelines router POSTs to /guidance/test-patients/replay with the
SERVICE_AUTH_SECRET Bearer header so the core-api can authenticate the
inter-service call (DI-LEO-AI-167).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.terminology_api.app.routers import guidelines as guidelines_router
from services.terminology_api.app.services.guideline_compiler import CompileScope


@pytest.mark.asyncio
async def test_replay_hook_sends_service_auth_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "super-secret-shared-token")
    monkeypatch.delenv("DISABLE_TEST_PATIENT_REPLAY", raising=False)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = "{}"

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(
        guidelines_router.httpx, "AsyncClient", return_value=fake_client
    ):
        await guidelines_router._trigger_test_patient_replay(
            "v20260419-081408",
            CompileScope.from_values("guideline", "NG12"),
        )

    assert fake_client.post.await_count == 1
    _, kwargs = fake_client.post.await_args
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer super-secret-shared-token"
    assert headers["X-Requested-With"] == "XMLHttpRequest"


@pytest.mark.asyncio
async def test_replay_hook_omits_auth_header_when_secret_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local dev parity: with no SERVICE_AUTH_SECRET, the call still goes out
    (the secret is the boundary in deployed environments) but no Authorization
    header is added."""
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)
    monkeypatch.delenv("DISABLE_TEST_PATIENT_REPLAY", raising=False)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = "{}"

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(
        guidelines_router.httpx, "AsyncClient", return_value=fake_client
    ):
        await guidelines_router._trigger_test_patient_replay(
            "v20260419-081408",
            CompileScope.from_values("guideline", "NG12"),
        )

    _, kwargs = fake_client.post.await_args
    assert "Authorization" not in kwargs["headers"]


@pytest.mark.asyncio
async def test_replay_hook_swallows_401_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 401 from core-api must be logged at WARNING but never raised --
    a failed replay must not block a successful compile (DI-LEO-AI-167)."""
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "wrong-secret")
    monkeypatch.delenv("DISABLE_TEST_PATIENT_REPLAY", raising=False)

    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.text = '{"detail":"Invalid service auth token"}'

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    with patch.object(
        guidelines_router.httpx, "AsyncClient", return_value=fake_client
    ), caplog.at_level("WARNING"):
        await guidelines_router._trigger_test_patient_replay(
            "v1", CompileScope.from_values("guideline", "NG12")
        )

    assert any(
        "Test patient replay returned 401" in rec.getMessage()
        for rec in caplog.records
    )
