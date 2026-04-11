"""Tests for domain source filter and delete protection -- VT-LEO-AI-066.

Verifies:
  - GET /domains?source= returns filtered results
  - DELETE /domains/{id} returns 403 for NICE and platform domains
  - POST /domains creates domain with source='tenant'
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.domains import router

# ── Test app setup ───────────────────────────────────────────────────────


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def test_client():
    return TestClient(_make_app())


def _kg_run_mock(rows):
    """Return a KnowledgeGraphClient mock whose run() returns rows."""
    client = MagicMock()
    client.run.return_value = rows
    client.close = MagicMock()
    return client


# ── Source filter tests ───────────────────────────────────────────────────


class TestDomainSourceFilter:
    """GET /domains?source="""

    def test_returns_all_domains_when_no_filter(self, test_client):
        """GET /domains without source param returns all domains."""
        domains = [
            {
                "id": "cancer_audit",
                "name": "Cancer Audit",
                "description": "",
                "source": "platform",
                "subdomain_count": 3,
            },
            {
                "id": "nice:cancer",
                "name": "Cancer",
                "description": "",
                "source": "nice",
                "subdomain_count": 0,
            },
        ]

        with (
            patch("app.routers.domains.KnowledgeGraphClient") as mock_cls,
            patch("app.routers.domains._ensure_default_domain"),
        ):
            mock_cls.return_value = _kg_run_mock(domains)
            resp = test_client.get("/domains")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

    def test_source_filter_passed_to_cypher(self, test_client):
        """GET /domains?source=nice passes source param to Neo4j Cypher."""
        nice_domain = [
            {
                "id": "nice:cancer",
                "name": "Cancer",
                "description": "",
                "source": "nice",
                "subdomain_count": 0,
            },
        ]

        with (
            patch("app.routers.domains.KnowledgeGraphClient") as mock_cls,
            patch("app.routers.domains._ensure_default_domain"),
        ):
            mock_client = MagicMock()
            mock_client.run.return_value = nice_domain
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.get("/domains?source=nice")

        assert resp.status_code == 200
        # Verify the run call included the source parameter
        call_kwargs = mock_client.run.call_args
        assert call_kwargs is not None
        # source arg should be passed
        args_or_kwargs = call_kwargs[0] if call_kwargs[0] else call_kwargs[1]
        assert "nice" in str(args_or_kwargs) or "nice" in str(call_kwargs[1])

    def test_domain_response_includes_source_field(self, test_client):
        """GET /domains returns source field in each domain."""
        domains = [
            {
                "id": "cancer_audit",
                "name": "Cancer Audit",
                "description": "",
                "source": "platform",
                "subdomain_count": 2,
            },
        ]

        with (
            patch("app.routers.domains.KnowledgeGraphClient") as mock_cls,
            patch("app.routers.domains._ensure_default_domain"),
        ):
            mock_cls.return_value = _kg_run_mock(domains)
            resp = test_client.get("/domains")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["source"] == "platform"


# ── Delete protection tests ───────────────────────────────────────────────


class TestDomainDeleteProtection:
    """DELETE /domains/{id} source protection."""

    def test_delete_nice_domain_returns_403(self, test_client):
        """DELETE should return 403 for NICE-sourced domains."""
        with patch("app.routers.domains.KnowledgeGraphClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.run.return_value = [{"id": "nice:cancer", "source": "nice"}]
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.delete("/domains/nice:cancer")

        assert resp.status_code == 403
        assert "cannot be deleted" in resp.json()["detail"].lower()

    def test_delete_platform_domain_returns_403(self, test_client):
        """DELETE should return 403 for platform-sourced domains."""
        with patch("app.routers.domains.KnowledgeGraphClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.run.return_value = [
                {"id": "cancer_audit", "source": "platform"}
            ]
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.delete("/domains/cancer_audit")

        assert resp.status_code == 403

    def test_delete_tenant_domain_succeeds(self, test_client):
        """DELETE should succeed for tenant-sourced domains."""
        with patch("app.routers.domains.KnowledgeGraphClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.run.side_effect = [
                [{"id": "my_domain", "source": "tenant"}],  # existence check
                [],  # DETACH DELETE
            ]
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.delete("/domains/my_domain")

        assert resp.status_code == 204

    def test_delete_nonexistent_domain_returns_404(self, test_client):
        """DELETE should return 404 when domain does not exist."""
        with patch("app.routers.domains.KnowledgeGraphClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.run.return_value = []  # domain not found
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.delete("/domains/does-not-exist")

        assert resp.status_code == 404


# ── Create domain tests ───────────────────────────────────────────────────


class TestDomainCreate:
    """POST /domains source defaults."""

    def test_create_domain_defaults_to_tenant_source(self, test_client):
        """POST /domains creates domain with source='tenant' by default."""
        with patch("app.routers.domains.KnowledgeGraphClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.run.side_effect = [
                [],  # existence check (domain doesn't exist)
                [],  # CREATE call
            ]
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.post(
                "/domains",
                json={"name": "My New Domain", "description": "Test domain"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["source"] == "tenant"

    def test_create_domain_returns_400_on_duplicate(self, test_client):
        """POST /domains returns 400 when domain name already exists."""
        with patch("app.routers.domains.KnowledgeGraphClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.run.return_value = [{"id": "my_new_domain"}]  # already exists
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            resp = test_client.post(
                "/domains",
                json={"name": "My New Domain", "description": ""},
            )

        assert resp.status_code == 400
