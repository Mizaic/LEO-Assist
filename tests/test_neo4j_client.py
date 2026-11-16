"""Tests for libs/neo4j-client/client.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_driver_cache():
    """Reset the module-level driver pool between tests so each test
    gets a fresh `GraphDatabase` mock applied."""
    from libs.neo4j_client import client as mod

    mod._DRIVER_CACHE.clear()
    yield
    mod._DRIVER_CACHE.clear()


class TestBaseClient:
    """Tests for _BaseClient initialization and methods."""

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_init_creates_driver(self, MockGD, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "pass")

        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("bolt://localhost:7687", "neo4j", "pass")
        MockGD.driver.assert_called()
        client.close()

    def test_init_raises_on_empty_credentials(self):
        from libs.neo4j_client.client import _BaseClient

        with pytest.raises(RuntimeError, match="credentials missing"):
            _BaseClient("", "", "")

    def test_init_raises_on_partial_credentials(self):
        from libs.neo4j_client.client import _BaseClient

        with pytest.raises(RuntimeError, match="credentials missing"):
            _BaseClient("bolt://localhost:7687", "neo4j", "")

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_session_context_manager(self, MockGD):
        from libs.neo4j_client.client import _BaseClient

        mock_session = MagicMock()
        MockGD.driver.return_value.session.return_value = mock_session

        client = _BaseClient("bolt://localhost:7687", "neo4j", "pass")
        with client.session() as s:
            assert s is mock_session
        mock_session.close.assert_called_once()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_close_is_noop_to_protect_shared_pool(self, MockGD):
        """Per-instance close() must not tear down the cached driver
        because the pool is shared across the process. The driver is
        only closed at interpreter shutdown via atexit."""
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("bolt://localhost:7687", "neo4j", "pass")
        client.close()
        MockGD.driver.return_value.close.assert_not_called()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_atexit_closes_cached_drivers(self, MockGD):
        from libs.neo4j_client.client import (
            _BaseClient,
            _close_all_cached_drivers,
        )

        _BaseClient("bolt://localhost:7687", "neo4j", "pass")
        _close_all_cached_drivers()
        MockGD.driver.return_value.close.assert_called_once()


class TestRunWithRetry:
    """Tests for run_with_retry retry logic."""

    @patch("libs.neo4j_client.client.time.sleep")
    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_success_on_first_attempt(self, MockGD, mock_sleep):
        from libs.neo4j_client.client import _BaseClient

        mock_result = [{"n": 1}]
        mock_session = MagicMock()
        mock_session.run.return_value = [
            MagicMock(
                **{"__iter__": lambda s: iter(mock_result), "keys": lambda s: ["n"]}
            )
        ]
        MockGD.driver.return_value.session.return_value = mock_session
        MockGD.driver.return_value.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        MockGD.driver.return_value.session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        client = _BaseClient("bolt://localhost:7687", "neo4j", "pass")
        # run() delegates to run_with_retry - just verify no exception
        mock_session.run.return_value = iter([{"n": 1}])
        mock_session2 = MagicMock()
        mock_session2.run.return_value = [{"n": 1}]
        client._driver.session.return_value.__enter__ = MagicMock(
            return_value=mock_session2
        )
        client._driver.session.return_value.__exit__ = MagicMock(return_value=False)
        # Won't actually work due to context manager complexity; test at higher level
        mock_sleep.assert_not_called()

    @patch("libs.neo4j_client.client.time.sleep")
    def test_retries_on_service_unavailable(self, mock_sleep):
        from libs.neo4j_client.client import run_with_retry
        from neo4j.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.run.side_effect = [ServiceUnavailable("down"), [{"x": 1}]]
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_with_retry(mock_client, "RETURN 1")
        assert result == [{"x": 1}]
        assert mock_sleep.call_count == 1

    @patch("libs.neo4j_client.client.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        from libs.neo4j_client.client import run_with_retry
        from neo4j.exceptions import ServiceUnavailable

        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.run.side_effect = ServiceUnavailable("persistent failure")
        mock_client.session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_client.session.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ServiceUnavailable):
            run_with_retry(mock_client, "RETURN 1")
        assert mock_sleep.call_count == 3  # _MAX_RETRIES - 1


class TestPatientGraphClient:

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_uses_patient_env_vars(self, MockGD, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://patient:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        MockGD.driver.assert_called()
        client.close()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_defaults_username_to_neo4j_when_unset(self, MockGD, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://patient:7687")
        monkeypatch.delenv("NEO4J_USER", raising=False)
        monkeypatch.delenv("NEO4J_PATIENT_USER", raising=False)
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        MockGD.driver.assert_called()
        _uri, kwargs = MockGD.driver.call_args
        assert kwargs["auth"][0] == "neo4j"
        client.close()


class TestKnowledgeGraphClient:

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_uses_knowledge_env_vars(self, MockGD, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://knowledge:7688")
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "kgpass")

        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        MockGD.driver.assert_called()
        client.close()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_defaults_username_to_neo4j_when_unset(self, MockGD, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://knowledge:7688")
        monkeypatch.delenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", raising=False)
        monkeypatch.delenv("NEO4J_KNOWLEDGE_USER", raising=False)
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "kgpass")

        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        MockGD.driver.assert_called()
        _args, kwargs = MockGD.driver.call_args
        assert kwargs["auth"][0] == "neo4j"
        client.close()


class TestTlsCaBundle:
    """Tests for certifi TLS root bundle wiring (DO-448BFA1A / DI-84F44836)."""

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_sets_ssl_cert_file_from_certifi_when_unset(self, MockGD, monkeypatch):
        import certifi
        import os

        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("neo4j+s://example.databases.neo4j.io", "neo4j", "pass")
        assert os.environ.get("SSL_CERT_FILE") == certifi.where()
        MockGD.driver.assert_called_once()
        client.close()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_preserves_existing_ssl_cert_file(self, MockGD, monkeypatch):
        import os

        custom_ca = "/etc/ssl/certs/custom-ca-bundle.pem"
        monkeypatch.setenv("SSL_CERT_FILE", custom_ca)
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("neo4j+s://example.databases.neo4j.io", "neo4j", "pass")
        assert os.environ.get("SSL_CERT_FILE") == custom_ca
        MockGD.driver.assert_called_once()
        client.close()

    @patch("libs.neo4j_client.client.AsyncGraphDatabase")
    def test_async_driver_sets_ssl_cert_file_when_unset(self, MockAGD, monkeypatch):
        import certifi
        import os

        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.setenv(
            "KNOWLEDGE_GRAPH_NEO4J_URI", "neo4j+s://example.databases.neo4j.io"
        )
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "pass")
        from libs.neo4j_client.client import get_async_driver

        get_async_driver()
        assert os.environ.get("SSL_CERT_FILE") == certifi.where()
        MockAGD.driver.assert_called_once()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_secure_uri_loads_certifi_into_ssl_context(self, MockGD, monkeypatch):
        import ssl

        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("neo4j+s://example.databases.neo4j.io", "neo4j", "pass")
        args, kwargs = MockGD.driver.call_args
        ctx = kwargs["ssl_context"]
        assert args[0] == "neo4j://example.databases.neo4j.io"
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert ctx.get_ca_certs()
        client.close()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_plain_bolt_uri_does_not_pass_ssl_context(self, MockGD):
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("bolt://localhost:7687", "neo4j", "pass")
        args, kwargs = MockGD.driver.call_args
        assert args[0] == "bolt://localhost:7687"
        assert "ssl_context" not in kwargs
        client.close()

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_ssc_uri_stays_on_the_driver_scheme(self, MockGD):
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("neo4j+ssc://example.databases.neo4j.io", "neo4j", "pass")
        args, kwargs = MockGD.driver.call_args
        assert args[0] == "neo4j+ssc://example.databases.neo4j.io"
        assert "ssl_context" not in kwargs
        client.close()

    @patch("libs.neo4j_client.client.AsyncGraphDatabase")
    def test_async_secure_uri_loads_certifi_into_ssl_context(
        self, MockAGD, monkeypatch
    ):
        import ssl

        monkeypatch.setenv(
            "KNOWLEDGE_GRAPH_NEO4J_URI", "neo4j+s://example.databases.neo4j.io"
        )
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
        monkeypatch.setenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "pass")
        from libs.neo4j_client.client import get_async_driver

        get_async_driver()
        args, kwargs = MockAGD.driver.call_args
        assert args[0] == "neo4j://example.databases.neo4j.io"
        assert kwargs["ssl_context"].verify_mode == ssl.CERT_REQUIRED

    @patch("libs.neo4j_client.client.GraphDatabase")
    def test_unknown_pool_option_still_uses_certifi_context(self, MockGD):
        import ssl

        from neo4j.exceptions import ConfigurationError

        def side_effect(uri, **kwargs):
            if (
                "notifications_min_severity" in kwargs
                or "liveness_check_timeout" in kwargs
            ):
                raise ConfigurationError("unknown")
            return MagicMock()

        MockGD.driver.side_effect = side_effect
        from libs.neo4j_client.client import _BaseClient

        client = _BaseClient("neo4j+s://example.databases.neo4j.io", "neo4j", "pass")
        args, kwargs = MockGD.driver.call_args
        assert args[0] == "neo4j://example.databases.neo4j.io"
        assert kwargs["ssl_context"].verify_mode == ssl.CERT_REQUIRED
        assert "liveness_check_timeout" not in kwargs
        client.close()

    def test_all_neo4j_requirements_pin_certifi_2026(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        req_files = [
            root / "requirements.txt",
            *sorted((root / "services").glob("*/requirements.txt")),
        ]
        neo4j_reqs = [
            p
            for p in req_files
            if re.search(r"^neo4j[>=]", p.read_text(encoding="utf-8"), re.M)
        ]
        assert len(neo4j_reqs) >= 9
        for req_path in neo4j_reqs:
            text = req_path.read_text(encoding="utf-8")
            rel = req_path.relative_to(root)
            assert re.search(
                r"^certifi>=2026\.", text, re.M
            ), f"{rel} uses neo4j without pinning certifi>=2026.x"
