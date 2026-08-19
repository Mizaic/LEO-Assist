"""Startup preflight for shared runtime dependencies.

Atlas trace:
  DO: DO-9F3CD7DE
  DI: DI-9456E5BE

Logs each check as ok/fail/wait. Config and import misses fail at once.
Redis and Neo4j can wait a few seconds. This service does not wait for
core-api or terminology-api.
"""

from __future__ import annotations

import importlib
import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

logger = logging.getLogger("libs.startup.preflight")

SleepFn = Callable[[float], None]
CheckFn = Callable[[], "CheckResult"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    wait: bool
    detail: str


class PreflightError(RuntimeError):
    """Raised when a required startup check fails in strict mode."""


def _is_local() -> bool:
    return os.getenv("ENVIRONMENT", "local").strip().lower() == "local"


def _strict() -> bool:
    flag = os.getenv("STARTUP_PREFLIGHT_STRICT", "").strip().lower()
    if flag in {"true", "1", "yes"}:
        return True
    if flag in {"false", "0", "no"}:
        return False
    return not _is_local()


def check_import(module_name: str) -> CheckResult:
    try:
        importlib.import_module(module_name)
    except ImportError:
        return CheckResult(
            module_name,
            False,
            False,
            "module missing; rebuild the image",
        )
    return CheckResult(module_name, True, False, "importable")


def check_session_namespace(*, required: bool) -> CheckResult:
    namespace = os.getenv("SESSION_KEY_NAMESPACE", "").strip()
    if namespace:
        return CheckResult(
            "session_namespace",
            True,
            False,
            f"set name={namespace}",
        )
    if required:
        return CheckResult(
            "session_namespace",
            False,
            False,
            "unset; inter-service calls will 401",
        )
    return CheckResult(
        "session_namespace",
        True,
        False,
        "unset; import-time fallback in use",
    )


def check_redis() -> CheckResult:
    if not (os.getenv("REDIS_URL") or "").strip():
        return CheckResult("redis", False, False, "REDIS_URL unset")
    try:
        import redis

        client = redis.from_url(
            os.environ["REDIS_URL"],
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        client.close()
    except Exception as exc:
        return CheckResult(
            "redis",
            False,
            True,
            f"unreachable: {type(exc).__name__}",
        )
    return CheckResult("redis", True, True, "ping ok")


def check_neo4j_patient() -> CheckResult:
    if not (os.getenv("NEO4J_URI") or "").strip():
        return CheckResult("neo4j_patient", False, False, "NEO4J_URI unset")
    try:
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        try:
            client.run("RETURN 1 AS ok")
        finally:
            client.close()
    except Exception as exc:
        return CheckResult(
            "neo4j_patient",
            False,
            True,
            f"unreachable: {type(exc).__name__}",
        )
    return CheckResult("neo4j_patient", True, True, "query ok")


def _log_result(result: CheckResult, *, waiting: bool = False) -> None:
    wait_flag = "yes" if result.wait else "no"
    if result.ok:
        logger.info("preflight.ok name=%s wait=%s %s", result.name, wait_flag, result.detail)
        return
    if waiting:
        logger.warning(
            "preflight.wait name=%s wait=%s %s",
            result.name,
            wait_flag,
            result.detail,
        )
        return
    logger.error("preflight.fail name=%s wait=%s %s", result.name, wait_flag, result.detail)


def _run_one(check: CheckFn, attempts: int, interval_s: float, sleep: SleepFn) -> CheckResult:
    result = check()
    if result.ok or not result.wait:
        _log_result(result)
        return result
    for attempt in range(1, attempts + 1):
        _log_result(result, waiting=True)
        logger.info("preflight.retry name=%s attempt=%s/%s", result.name, attempt, attempts)
        if attempt >= attempts:
            break
        sleep(interval_s)
        result = check()
        if result.ok:
            _log_result(result)
            return result
    _log_result(result)
    return result


def run_checks(
    checks: Sequence[CheckFn],
    *,
    strict: bool,
    attempts: int = 3,
    interval_s: float = 2.0,
    sleep: SleepFn = time.sleep,
) -> list[CheckResult]:
    results = [_run_one(check, attempts, interval_s, sleep) for check in checks]
    failed = [item.name for item in results if not item.ok]
    if failed and strict:
        raise PreflightError("startup preflight failed: " + ",".join(failed))
    if failed:
        logger.warning("preflight.continue failed=%s strict=false", ",".join(failed))
    else:
        logger.info("preflight.done failed=0")
    return results


def run_analytics_preflight(
    *,
    sleep: SleepFn = time.sleep,
    attempts: int | None = None,
    interval_s: float | None = None,
) -> list[CheckResult]:
    """Block analytics startup until required local deps are visible."""
    strict = _strict()
    retry_attempts = attempts or int(os.getenv("STARTUP_PREFLIGHT_ATTEMPTS", "3"))
    retry_interval = interval_s or float(os.getenv("STARTUP_PREFLIGHT_INTERVAL_S", "2"))
    logger.info(
        "preflight.begin service=analytics-api env=%s strict=%s "
        "waits_for=redis,neo4j_patient does_not_wait_for=core-api,terminology-api",
        os.getenv("ENVIRONMENT", "local"),
        str(strict).lower(),
    )
    checks: list[CheckFn] = [
        lambda: check_import("jsonschema"),
        lambda: check_session_namespace(required=strict),
        check_redis,
        check_neo4j_patient,
    ]
    return run_checks(
        checks,
        strict=strict,
        attempts=retry_attempts,
        interval_s=retry_interval,
        sleep=sleep,
    )
