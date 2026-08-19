"""Startup preflight: required config fails fast, runtime deps can wait.

Atlas trace:
  DO: DO-9F3CD7DE
  DI: DI-9456E5BE
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.startup.preflight import (
    CheckResult,
    PreflightError,
    check_import,
    check_redis,
    check_session_namespace,
    run_analytics_preflight,
    run_checks,
)


def test_import_check_fails_without_wait() -> None:
    result = check_import("definitely_missing_module_xyz")
    assert result.ok is False
    assert result.wait is False
    assert result.name == "definitely_missing_module_xyz"


def test_redis_unset_is_config_miss_not_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    result = check_redis()
    assert result.ok is False
    assert result.wait is False
    assert result.detail == "REDIS_URL unset"


def test_session_namespace_required_when_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SESSION_KEY_NAMESPACE", raising=False)
    result = check_session_namespace(required=True)
    assert result.ok is False
    assert result.wait is False


def test_session_namespace_optional_when_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SESSION_KEY_NAMESPACE", raising=False)
    result = check_session_namespace(required=False)
    assert result.ok is True


def test_run_checks_retries_waitable_then_passes() -> None:
    calls = {"n": 0}

    def flaky() -> CheckResult:
        calls["n"] += 1
        if calls["n"] < 3:
            return CheckResult("redis", False, True, "unreachable: Timeout")
        return CheckResult("redis", True, True, "ping ok")

    slept: list[float] = []
    results = run_checks([flaky], strict=True, attempts=3, interval_s=0.01, sleep=slept.append)
    assert results[0].ok is True
    assert calls["n"] == 3
    assert slept == [0.01, 0.01]


def test_run_checks_strict_raises_on_config_miss() -> None:
    def missing() -> CheckResult:
        return CheckResult("jsonschema", False, False, "module missing")

    with pytest.raises(PreflightError, match="jsonschema"):
        run_checks([missing], strict=True, attempts=1, sleep=lambda _s: None)


def test_run_checks_nonstrict_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")

    def missing() -> CheckResult:
        return CheckResult("redis", False, False, "REDIS_URL unset")

    results = run_checks([missing], strict=False, attempts=1, sleep=lambda _s: None)
    assert results[0].ok is False
    assert "preflight.fail" in caplog.text


def test_analytics_preflight_logs_wait_order(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("SESSION_KEY_NAMESPACE", "leo-ai-audit")
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid")
    with (
        patch("libs.startup.preflight.check_redis", return_value=CheckResult("redis", True, True, "ping ok")),
        patch(
            "libs.startup.preflight.check_neo4j_patient",
            return_value=CheckResult("neo4j_patient", True, True, "query ok"),
        ),
    ):
        run_analytics_preflight(sleep=lambda _s: None)
    assert "waits_for=redis,neo4j_patient" in caplog.text
    assert "does_not_wait_for=core-api,terminology-api" in caplog.text
    assert "redis://" not in caplog.text


def test_analytics_preflight_strict_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "val")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("SESSION_KEY_NAMESPACE", "leo-ai-audit")
    with (
        patch(
            "libs.startup.preflight.check_neo4j_patient",
            return_value=CheckResult("neo4j_patient", True, True, "query ok"),
        ),
        pytest.raises(PreflightError),
    ):
        run_analytics_preflight(sleep=lambda _s: None)


def test_preflight_logs_do_not_include_email_or_url(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("REDIS_URL", "rediss://secret:password@redis.example:6380")
    client = MagicMock()
    client.ping.return_value = True
    with patch("redis.from_url", return_value=client):
        check_redis()
        run_checks(
            [lambda: check_redis()],
            strict=False,
            attempts=1,
            sleep=lambda _s: None,
        )
    assert "password" not in caplog.text
    assert "redis.example" not in caplog.text
