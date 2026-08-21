"""Shared test fixtures for the consolidated platform tests."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest


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
