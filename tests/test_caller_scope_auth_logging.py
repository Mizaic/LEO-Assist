"""401 reason logging for inter-service session scope.

Atlas trace:
  DO: DO-DB7F8D52
  DI: DI-4DBE1A18, DI-9456E5BE
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from libs.auth.org_scope import get_caller_scope


def _assert_no_secrets(text: str) -> None:
    assert "secret-session-id" not in text
    assert "clinician@nhs.net" not in text


def test_missing_session_header_logs_reason(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="libs.auth.org_scope")
    with pytest.raises(HTTPException) as exc:
        get_caller_scope(leo_session=None)
    assert exc.value.status_code == 401
    assert "reason=missing_session_header" in caplog.text
    _assert_no_secrets(caplog.text)


def test_session_not_found_logs_namespace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="libs.auth.org_scope")
    with (
        patch(
            "libs.redis_client.session.lookup_session",
            return_value=(None, "session_not_found"),
        ),
        patch("libs.redis_client.session.SESSION_NAMESPACE", "leo-ai-audit"),
        pytest.raises(HTTPException) as exc,
    ):
        get_caller_scope(leo_session="secret-session-id")
    assert exc.value.status_code == 401
    assert "reason=session_not_found" in caplog.text
    assert "namespace=leo-ai-audit" in caplog.text
    _assert_no_secrets(caplog.text)


def test_redis_url_unset_logs_reason(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="libs.auth.org_scope")
    with (
        patch(
            "libs.redis_client.session.lookup_session",
            return_value=(None, "redis_url_unset"),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        get_caller_scope(leo_session="secret-session-id")
    assert exc.value.status_code == 401
    assert "reason=redis_url_unset" in caplog.text
    _assert_no_secrets(caplog.text)


def test_session_missing_email_logs_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="libs.auth.org_scope")
    with (
        patch(
            "libs.redis_client.session.lookup_session",
            return_value=({"email": ""}, "ok"),
        ),
        pytest.raises(HTTPException) as exc,
    ):
        get_caller_scope(leo_session="secret-session-id")
    assert exc.value.detail == "Session has no user email"
    assert "reason=session_missing_email" in caplog.text
    _assert_no_secrets(caplog.text)


def test_unknown_user_logs_reason_without_email(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="libs.auth.org_scope")
    client = MagicMock()
    client.run.return_value = []
    with (
        patch(
            "libs.redis_client.session.lookup_session",
            return_value=({"email": "clinician@nhs.net"}, "ok"),
        ),
        patch("libs.auth.org_scope._cache_get", return_value=None),
        patch("libs.auth.org_scope._cache_put"),
        patch("libs.auth.org_scope.PatientGraphClient", return_value=client),
        pytest.raises(HTTPException) as exc,
    ):
        get_caller_scope(leo_session="secret-session-id")
    assert exc.value.detail == "Unknown user"
    assert "reason=unknown_user" in caplog.text
    _assert_no_secrets(caplog.text)
