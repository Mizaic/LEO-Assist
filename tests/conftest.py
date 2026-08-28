"""Shared test fixtures for the consolidated platform tests."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_APP_ROOT = _REPO_ROOT / "services" / "api"
_ANALYTICS_APP_ROOT = _REPO_ROOT / "services" / "analytics_api"

_ENV_BEFORE_COLLECTION: dict[str, str] = {}


def pytest_configure(config: pytest.Config) -> None:
    """Snapshot ``os.environ`` before any test module is imported."""
    _ENV_BEFORE_COLLECTION.clear()
    _ENV_BEFORE_COLLECTION.update(os.environ)


def pytest_collection_finish(session: pytest.Session) -> None:
    """Undo ``os.environ`` writes made while importing test modules.

    Collection imports every test module. A module that calls
    ``load_dotenv()`` at import time -- directly, or by exec'ing a
    script that does -- writes the developer's local ``.env`` into
    ``os.environ`` before a single test runs. ``monkeypatch`` cannot
    undo that, because it happened before any fixture existed, so the
    whole session silently inherits it.

    That is not a tidiness problem. The repo-root ``.env`` sets
    ``LEO_LOCAL_DEV_BYPASS=true``, which makes ``get_caller_scope``
    return an admin bypass scope instead of refusing the request. Every
    test that asserts auth is refused then passes for the wrong reason,
    so the suite reports the code as safer than it is.

    Restoring the pre-collection snapshot here makes the leak
    structurally impossible: it runs after all imports and before the
    first test, so no import-time env write can reach a test, whichever
    module made it.
    """
    if not _ENV_BEFORE_COLLECTION:
        return
    os.environ.clear()
    os.environ.update(_ENV_BEFORE_COLLECTION)


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


@pytest.fixture(autouse=True)
def _reset_capability_registry():
    """Stop one test's patched subgraph registry poisoning every later test.

    ``get_capability_registry()`` caches its result in the module global
    ``_default_capability_registry``, and builds it by iterating
    ``libs.pipeline_graph.registry.get_registry().list_subgraphs()``. A
    test that patches ``get_registry`` with a ``MagicMock`` -- as the
    durable-runner parity tests do -- makes ``list_subgraphs()`` yield
    nothing, so the cached registry ends up holding only the two builtin
    capabilities. ``patch`` restores ``get_registry`` on exit, but the
    empty registry stays cached in the *other* module, where no teardown
    ever touches it.

    Every later plan validation then reports each clinical stage
    (extraction, post_processing, terminology, persist, ...) as an
    unregistered capability, so a plan version silently fails to
    publish. Clearing the cache either side of each test keeps a
    poisoned build inside the test that caused it.
    """
    import libs.pipeline_graph.capability_registry as capability_registry_mod

    capability_registry_mod._default_capability_registry = None
    yield
    capability_registry_mod._default_capability_registry = None


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
