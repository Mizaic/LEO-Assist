"""Tests for `libs/agent_config/loader.py`.

Atlas trace:
  DO: DO-61EE87E0
  DI: DI-6A1CD328

We mock the KnowledgeGraphClient so the loader can be exercised
without a live Neo4j. The loader's job is straightforward:
  - active Devices -> AgentConfig keyed by type_code
  - all Measures   -> dict keyed by id
  - all ValueSets  -> dict keyed by id
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.agent_config.loader import FHIRConfigLoader
from libs.agent_config.models import AgentConfig, FHIRConfig


def _device_resource(
    rid: str, code: str, display: str = "", status: str = "active"
) -> dict:
    return {
        "id": rid,
        "status": status,
        "type": {"coding": [{"code": code, "display": display}]},
        "version": [{"value": "1.0.0"}],
    }


@pytest.fixture
def fake_client():
    return MagicMock()


@pytest.fixture
def loader(fake_client):
    return FHIRConfigLoader(client=fake_client)


class TestLoadDevices:
    def test_active_devices_become_agents_keyed_by_type_code(
        self, loader, fake_client
    ):
        def _run(query, **kw):
            if "Device" in query:
                return [
                    {"resource": _device_resource("d1", "ner", "NER agent")},
                    {"resource": _device_resource("d2", "summary", "Summary")},
                ]
            return []

        fake_client.run.side_effect = _run
        cfg = loader.load()
        assert isinstance(cfg, FHIRConfig)
        assert set(cfg.agents.keys()) == {"ner", "summary"}
        assert isinstance(cfg.agents["ner"], AgentConfig)
        assert cfg.agents["ner"].type_display == "NER agent"

    def test_devices_without_type_code_are_skipped(self, loader, fake_client):
        def _run(query, **kw):
            if "Device" in query:
                return [
                    {"resource": {"id": "d-bad", "status": "active",
                                  "type": {"coding": [{}]}}},
                    {"resource": _device_resource("d1", "ner")},
                ]
            return []

        fake_client.run.side_effect = _run
        cfg = loader.load()
        assert list(cfg.agents.keys()) == ["ner"]


class TestLoadResources:
    def test_measures_keyed_by_id(self, loader, fake_client):
        def _run(query, **kw):
            if "Measure" in query:
                return [
                    {"resource": {"id": "m1", "status": "active"}},
                    {"resource": {"id": "m2", "status": "active"}},
                ]
            return []

        fake_client.run.side_effect = _run
        cfg = loader.load()
        assert set(cfg.measures.keys()) == {"m1", "m2"}

    def test_resource_without_id_is_skipped(self, loader, fake_client):
        def _run(query, **kw):
            if "ValueSet" in query:
                return [
                    {"resource": {"status": "active"}},  # no id
                    {"resource": {"id": "vs1"}},
                ]
            return []

        fake_client.run.side_effect = _run
        cfg = loader.load()
        assert list(cfg.valuesets.keys()) == ["vs1"]


class TestLoadEmpty:
    def test_no_resources_returns_empty_config(self, loader, fake_client):
        fake_client.run.return_value = []
        cfg = loader.load()
        assert cfg.agents == {}
        assert cfg.measures == {}
        assert cfg.valuesets == {}


class TestActiveOnlyFilter:
    def test_device_query_filters_active_status(self, loader, fake_client):
        fake_client.run.return_value = []
        loader.load()
        called_queries = [c.args[0] for c in fake_client.run.call_args_list]
        device_queries = [q for q in called_queries if "Device" in q]
        assert any("active" in q for q in device_queries)
