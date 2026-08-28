"""Tests for libs.keyvault.loader startup secret loading.

When AZURE_KEYVAULT_URL is not set the loader must fall back to reading
secrets/.env.secrets so every service that calls load_keyvault_secrets()
ends up with a consistent environment, including SERVICE_AUTH_SECRET.

When AZURE_KEYVAULT_URL is set the loader must fail fast if Key Vault is
unreachable, auth fails, or required secrets are missing.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _restore_environ():
    """Put os.environ back the way it was found.

    ``load_keyvault_secrets`` writes straight into ``os.environ``, which
    monkeypatch cannot undo. Without this, values such as
    ``NEO4J_URI=from-kv`` leak into every later test in the session, and
    anything that builds a Neo4j client then fails on a URI with no
    scheme.
    """
    before = dict(os.environ)
    yield
    for key in set(os.environ) - set(before):
        os.environ.pop(key, None)
    os.environ.update(before)


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


def _stub_kv_client(monkeypatch, client_cls):
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", client_cls, raising=True)
    monkeypatch.setattr(
        "libs.azure.credentials.get_credential", lambda: object(), raising=True
    )


def test_fallback_loads_service_auth_secret_when_kv_disabled(
    loader_module, monkeypatch
):
    mod, secrets_file = loader_module
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
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
    """If AZURE_KEYVAULT_URL is set we must not also read the local file."""
    mod, secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")
    monkeypatch.delenv("SERVICE_AUTH_SECRET", raising=False)
    secrets_file.write_text("SERVICE_AUTH_SECRET=should-not-be-loaded\n")

    called = {"count": 0}

    class _FakeSecret:
        value = "from-kv"

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            called["count"] += 1
            return _FakeSecret()

    _stub_kv_client(monkeypatch, _FakeClient)

    mod.load_keyvault_secrets()

    assert called["count"] > 0
    assert os.environ.get("SERVICE_AUTH_SECRET") == "from-kv"


def test_kv_auth_failure_raises_startup_error(loader_module, monkeypatch):
    mod, secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")
    monkeypatch.delenv("NEO4J_URI", raising=False)
    secrets_file.write_text("NEO4J_URI=neo4j+s://local-fallback\n")

    called = {"count": 0}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            called["count"] += 1
            raise RuntimeError(
                "DefaultAzureCredential failed to retrieve a token "
                "from the included credentials. AADSTS70043: The refresh "
                "token has expired"
            )

    _stub_kv_client(monkeypatch, _FakeClient)

    with pytest.raises(mod.KeyVaultStartupError, match="authentication failed"):
        mod.load_keyvault_secrets()

    assert called["count"] == 1
    assert "NEO4J_URI" not in os.environ


def test_kv_missing_required_secret_raises_startup_error(loader_module, monkeypatch):
    mod, _secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")

    class _MissingSecret(Exception):
        pass

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            if name == "neo4j-patient-uri":
                raise _MissingSecret(
                    "(SecretNotFound) A secret with (name/id) "
                    "neo4j-patient-uri was not found in this key vault."
                )

            class _Secret:
                value = "from-kv"

            return _Secret()

    _stub_kv_client(monkeypatch, _FakeClient)

    with pytest.raises(mod.KeyVaultStartupError, match="missing required secrets"):
        mod.load_keyvault_secrets()


def test_kv_connection_error_raises_startup_error(loader_module, monkeypatch):
    mod, _secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            raise ConnectionError("Failed to reach key vault endpoint")

    _stub_kv_client(monkeypatch, _FakeClient)

    with pytest.raises(mod.KeyVaultStartupError, match="unreachable at startup"):
        mod.load_keyvault_secrets()


def test_kv_missing_sdk_raises_when_url_set(loader_module, monkeypatch):
    mod, _secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")

    import builtins

    real_import = builtins.__import__

    def _import_without_kv(name, *args, **kwargs):
        if name == "azure.keyvault.secrets":
            raise ModuleNotFoundError("azure-keyvault-secrets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import_without_kv)

    with pytest.raises(mod.KeyVaultStartupError, match="SDK is not installed"):
        mod.load_keyvault_secrets()


def test_kv_success_does_not_pull_in_unrelated_local_secrets(
    loader_module, monkeypatch
):
    """KV success must not read the local secrets file."""
    mod, secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")
    monkeypatch.delenv("NEO4J_URI", raising=False)
    secrets_file.write_text("NEO4J_URI=neo4j+s://should-not-be-used\n")

    class _FakeSecret:
        value = "from-kv"

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            return _FakeSecret()

    _stub_kv_client(monkeypatch, _FakeClient)

    mod.load_keyvault_secrets()

    assert os.environ.get("NEO4J_URI") == "from-kv"


def test_real_repo_secrets_file_path_resolves_correctly():
    """The module-level _LOCAL_SECRETS_FILE must resolve to <repo>/secrets/.env.secrets."""
    from libs.keyvault import loader as mod

    expected = Path(__file__).resolve().parent.parent / "secrets" / ".env.secrets"
    assert mod._LOCAL_SECRETS_FILE == expected


def test_optional_mail_graph_secret_not_found_is_quiet(
    loader_module, monkeypatch, caplog
):
    """Missing optional mail-graph secrets must not dump Azure stack text."""
    mod, _secrets_file = loader_module
    monkeypatch.setenv("AZURE_KEYVAULT_URL", "https://example.vault.azure.net/")

    class _MissingSecret(Exception):
        pass

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def get_secret(self, name):
            if name.startswith("mail-graph-"):
                raise _MissingSecret(
                    "(SecretNotFound) A secret with (name/id) "
                    f"{name} was not found in this key vault."
                )

            class _Secret:
                value = "from-kv"

            return _Secret()

    _stub_kv_client(monkeypatch, _FakeClient)

    with caplog.at_level(logging.INFO, logger="libs.keyvault.loader"):
        mod.load_keyvault_secrets()

    mail_logs = [r for r in caplog.records if "mail-graph-" in r.getMessage()]
    assert mail_logs
    assert all(r.levelno == logging.INFO for r in mail_logs)
    assert all("Optional KV secret" in r.getMessage() for r in mail_logs)
