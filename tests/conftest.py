"""Shared test fixtures for the consolidated platform tests."""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_APP_ROOT = _REPO_ROOT / "services" / "api"
_ANALYTICS_APP_ROOT = _REPO_ROOT / "services" / "analytics_api"


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set minimal environment for all tests."""
    monkeypatch.setenv("NEO4J_PATIENT_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PATIENT_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PATIENT_PASSWORD", "patient-dev")
    monkeypatch.setenv("NEO4J_KNOWLEDGE_URI", "bolt://localhost:7688")
    monkeypatch.setenv("NEO4J_KNOWLEDGE_USER", "neo4j")
    monkeypatch.setenv("NEO4J_KNOWLEDGE_PASSWORD", "knowledge-dev")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "test-tenant")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "test-client")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "test-secret")


@pytest.fixture(autouse=True)
def ensure_default_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def restore_real_redis_module() -> None:
    """Reload redis after a test stub, or leave it absent if not installed."""
    redis_mod = sys.modules.get("redis")
    if redis_mod is not None and callable(getattr(redis_mod, "from_url", None)):
        return
    sys.modules.pop("redis", None)
    try:
        importlib.import_module("redis")
    except ModuleNotFoundError:
        return


@pytest.fixture(autouse=True)
def _restore_real_redis_module():
    """Tests that stub sys.modules['redis'] can leave a fake module behind."""
    yield
    restore_real_redis_module()


def _purge_analytics_app_modules() -> None:
    marker = "services/analytics_api"
    for name in list(sys.modules):
        if name != "app" and not name.startswith("app."):
            continue
        mod = sys.modules.get(name)
        mod_file = (getattr(mod, "__file__", "") or "").replace("\\", "/")
        if marker in mod_file:
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _ensure_api_app_package():
    """Keep ``services/api`` as the default ``app`` package between tests."""
    _purge_analytics_app_modules()
    api_root = str(_API_APP_ROOT)
    while api_root in sys.path:
        sys.path.remove(api_root)
    sys.path.insert(0, api_root)
    yield
    _purge_analytics_app_modules()


@pytest.fixture
def mock_patient_graph():
    """Provide a mocked PatientGraphClient."""
    with patch("libs.neo4j_client.client.PatientGraphClient") as MockCls:
        instance = MagicMock()
        instance.run.return_value = []
        instance.session.return_value.__enter__ = MagicMock(return_value=MagicMock())
        instance.session.return_value.__exit__ = MagicMock(return_value=False)
        MockCls.return_value = instance
        yield instance


@pytest.fixture
def mock_knowledge_graph():
    """Provide a mocked KnowledgeGraphClient."""
    with patch("libs.neo4j_client.client.KnowledgeGraphClient") as MockCls:
        instance = MagicMock()
        instance.run.return_value = []
        MockCls.return_value = instance
        yield instance
