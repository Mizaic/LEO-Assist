"""Tests for the local-dev fallback in libs.keyvault.loader.

When AZURE_KEYVAULT_URL is not set the loader must fall back to reading
secrets/.env.secrets so every service that calls load_keyvault_secrets()
ends up with a consistent environment, including SERVICE_AUTH_SECRET.

Regression: without this fallback, services started under macOS Terminal.app
via `osascript do script` (which does NOT propagate parent shell env) ran
with an empty SERVICE_AUTH_SECRET. The result was 401 "Missing service auth
token" loops on every inter-service call to /reload, /extract, etc.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture
def loader_module(monkeypatch, tmp_path):
    """Import a fresh loader module pointed at a temp secrets/.env.secrets.

    The loader resolves the secrets path at import time from its own __file__,
    so we monkeypatch the module-level constant after import.
    """
    monkeypatch.delenv("AZURE_KEYVAULT_URL", raising=False)
    from libs.keyvault import loader as mod

    importlib.reload(mod)
    fake_secrets = tmp_path / ".env.secrets"
    monkeypatch.setattr(mod, "_LOCAL_SECRETS_FILE", fake_secrets, raising=True)
    return mod, fake_secrets


def test_fallback_loads_service_auth_secret_when_kv_disabled(
    loader_module, monkeypatch
):
    mod, secrets_file = loader_module
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)
    secrets_file.write_text(
        "# comment line\n"
        "SERVICE_AUTH_SECRET=abc123\n"
        "NEO4J_URI=neo4j+s://example\n"
        "\n"
        "EMPTY=\n"
    )

    mod.load_keyvault_secrets()

    assert os.environ.get("SERVICE_AUTH_SECRET") == "abc123"
    assert os.environ.get("NEO4J_URI") == "neo4j+s://example"
    assert os.environ.get("EMPTY") == ""


def test_fallback_does_not_overwrite_already_set_env(loader_module, monkeypatch):
    """Anything explicitly exported in the shell wins over the file."""
    mod, secrets_file = loader_module
    monkeypatch.setenv("SERVICE_AUTH_SECRET", "from-shell")
    secrets_file.write_text("SERVICE_AUTH_SECRET=from-file\n")

    mod.load_keyvault_secrets()

    assert os.environ.get("SERVICE_AUTH_SECRET") == "from-shell"


def test_fallback_is_safe_when_secrets_file_absent(loader_module, monkeypatch):
    """Missing .env.secrets must not raise -- production has no such file."""
    mod, secrets_file = loader_module
    assert not secrets_file.exists()
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)

    mod.load_keyvault_secrets()  # must not raise

    assert "SERVICE_AUTH_SECRET" not in os.environ


def test_fallback_skipped_when_kv_url_set(loader_module, monkeypatch):
    """If AZURE_KEYVAULT_URL is set we must not also read the local file --
    KV is the single source of truth in any deployed environment.
    """
    mod, secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)
    secrets_file.write_text("SERVICE_AUTH_SECRET=should-not-be-loaded\n")

    # Stub out the KV path so we don't actually call Azure.
    called = {"count": 0}

    class _FakeSecret:
        value = "from-kv"

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            called["count"] += 1
            return _FakeSecret()

    monkeypatch.setattr(
        "azure.keyvault.secrets.SecretClient", _FakeClient, raising=True
    )
    monkeypatch.setattr(
        "libs.azure.credentials.get_credential", lambda: object(), raising=True
    )

    mod.load_keyvault_secrets()

    assert called["count"] > 0
    assert os.environ.get("SERVICE_AUTH_SECRET") == "from-kv"


def test_real_repo_secrets_file_path_resolves_correctly():
    """The module-level _LOCAL_SECRETS_FILE must resolve to <repo>/secrets/.env.secrets."""
    from libs.keyvault import loader as mod

    expected = (
        Path(__file__).resolve().parent.parent / "secrets" / ".env.secrets"
    )
    assert mod._LOCAL_SECRETS_FILE == expected
