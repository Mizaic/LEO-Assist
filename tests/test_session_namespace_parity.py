"""VT-LEO-AI-217 -- Inter-service session namespace parity.

Covers DI-LEO-AI-229 / R-LEO-AI-210.

Verifies that:
1. The two Python session-namespace resolvers
   (libs/redis_client/session.py and services/api/app/services/session_store.py)
   agree on a single Redis key prefix for any given environment.
2. The deployed Bicep template
   (infra/bicep/modules/container-apps.bicep) injects SESSION_KEY_NAMESPACE
   into sharedEnv so every backend container app receives the value.

If this file fails, every inter-service auth call (X-Leo-Session) is at risk
of returning 401, which manifests in the UI as a post-login redirect loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import libs.redis_client.session as _libs_session  # noqa: E402
from app.services import session_store as _api_session_store  # noqa: E402

_NAMESPACE_VARS = (
    "SESSION_KEY_NAMESPACE",
    "ENVIRONMENT",
    "APP_ENV",
    "LEO_ENV",
    "FRONTEND_URL",
    "AUTH_REDIRECT_URI",
)


@pytest.fixture(autouse=True)
def _clear_namespace_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _NAMESPACE_VARS:
        monkeypatch.delenv(name, raising=False)


def _both_namespaces() -> tuple[str, str]:
    return (
        _libs_session._detect_session_namespace(),
        _api_session_store._detect_session_namespace(),
    )


def test_explicit_session_key_namespace_wins_on_both_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VT-217-TC-001: explicit SESSION_KEY_NAMESPACE overrides everything."""
    monkeypatch.setenv("SESSION_KEY_NAMESPACE", "leo-ai-audit")
    monkeypatch.setenv("ENVIRONMENT", "should-be-ignored")
    monkeypatch.setenv("FRONTEND_URL", "https://other-host.example.com")

    libs_ns, api_ns = _both_namespaces()

    assert libs_ns == "leo-ai-audit"
    assert api_ns == "leo-ai-audit"
    assert libs_ns == api_ns


@pytest.mark.parametrize("env_name", ["ENVIRONMENT", "APP_ENV", "LEO_ENV"])
def test_environment_fallback_parity(
    monkeypatch: pytest.MonkeyPatch, env_name: str
) -> None:
    """VT-217-TC-002: ENVIRONMENT / APP_ENV / LEO_ENV produce same namespace."""
    monkeypatch.setenv(env_name, "leo-ai-audit")

    libs_ns, api_ns = _both_namespaces()

    assert libs_ns == api_ns == "leo-ai-audit"


def test_frontend_url_host_derivation_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VT-217-TC-003: FRONTEND_URL host first label parity."""
    monkeypatch.setenv(
        "FRONTEND_URL", "https://leo-ai-audit.healthcarecopilot.ai"
    )

    libs_ns, api_ns = _both_namespaces()

    assert libs_ns == api_ns == "leo-ai-audit"


def test_auth_redirect_uri_without_scheme_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VT-217-TC-004: scheme-less AUTH_REDIRECT_URI normalises to a host."""
    monkeypatch.setenv(
        "AUTH_REDIRECT_URI",
        "leo-ai-audit.healthcarecopilot.ai/auth/callback",
    )

    libs_ns, api_ns = _both_namespaces()

    assert libs_ns == api_ns == "leo-ai-audit"


def test_total_fallback_to_local() -> None:
    """VT-217-TC-005: every relevant env var unset -> 'local' on both modules."""
    libs_ns, api_ns = _both_namespaces()

    assert libs_ns == "local"
    assert api_ns == "local"
    assert libs_ns == api_ns


def test_bicep_shared_env_includes_session_key_namespace() -> None:
    """VT-217-TC-006: container-apps.bicep injects SESSION_KEY_NAMESPACE."""
    bicep_path = (
        ROOT / "infra" / "bicep" / "modules" / "container-apps.bicep"
    )

    text = bicep_path.read_text(encoding="utf-8")

    # Bicep variable definition must exist (derived from frontendUrl).
    assert "var sessionKeyNamespace" in text, (
        "Bicep must define sessionKeyNamespace variable"
    )

    # SESSION_KEY_NAMESPACE must be declared inside sharedEnv, bound to it.
    shared_env_block = text.split("var sharedEnv")[1].split(
        "\nvar sharedSecrets"
    )[0]
    assert "SESSION_KEY_NAMESPACE" in shared_env_block, (
        "SESSION_KEY_NAMESPACE must be in sharedEnv"
    )
    assert "value: sessionKeyNamespace" in shared_env_block, (
        "SESSION_KEY_NAMESPACE must be bound to sessionKeyNamespace variable"
    )
