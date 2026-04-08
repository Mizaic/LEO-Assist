"""Structural contract tests for domain-driven episode detector configuration.

VT-LEO-AI-084 TC-004: DomainRegistry fail-fast when no ValueSet nodes found.
VT-LEO-AI-084 TC-006: episode_detector flag included in DomainSummary response model.
VT-LEO-AI-084 TC-007: assertion_filter included in SubdomainSummary/SubdomainDetail models.

These tests do not require a live Neo4j connection -- they validate model contracts,
Pydantic schemas, and fail-fast logic at the Python level.
"""

from __future__ import annotations

import pytest


class TestDomainRegistryFailFast:
    """VT-084-TC-004: registry raises when no ValueSet nodes found."""

    def test_registry_raises_when_no_valuesets(self):
        from unittest.mock import MagicMock, patch

        from libs.pipeline_graph.subgraphs.anchor import _load_registry
        from libs.domain_config.registry import DomainRegistry

        DomainRegistry.reset_instance()

        mock_kg = MagicMock()
        mock_kg.run.return_value = []  # empty for all queries

        with patch("libs.neo4j_client.client.KnowledgeGraphClient", return_value=mock_kg):
            with pytest.raises(RuntimeError, match="no ValueSet nodes found"):
                _load_registry()

    def test_registry_raises_when_domain_has_no_valuesets(self):
        from unittest.mock import MagicMock, patch

        from libs.pipeline_graph.subgraphs.anchor import _load_registry
        from libs.domain_config.registry import DomainRegistry

        DomainRegistry.reset_instance()

        mock_kg = MagicMock()
        mock_kg.run.return_value = []

        with patch("libs.neo4j_client.client.KnowledgeGraphClient", return_value=mock_kg):
            with pytest.raises(RuntimeError, match="no ValueSet nodes found.*cancer_audit"):
                _load_registry(domain_id="cancer_audit")

    def test_registry_succeeds_when_valuesets_present(self):
        import json
        from unittest.mock import MagicMock, patch

        from libs.pipeline_graph.subgraphs.anchor import _load_registry
        from libs.domain_config.registry import DomainRegistry

        DomainRegistry.reset_instance()

        fake_vs = {
            "resourceType": "ValueSet",
            "id": "ncda-cancer-types",
            "name": "cancer_types",
            "description": "Cancer type concepts",
            "compose": {"include": [{"system": "http://snomed.info/sct", "concept": []}]},
        }
        mock_kg = MagicMock()
        mock_kg.run.return_value = [
            {"id": "ncda-cancer-types", "raw_json": json.dumps(fake_vs)}
        ]

        with patch("libs.neo4j_client.client.KnowledgeGraphClient", return_value=mock_kg):
            registry = _load_registry(domain_id="cancer_audit")
        assert registry is not None

        DomainRegistry.reset_instance()

    def test_registry_without_domain_id_falls_back_to_episode_detector_domains(self):
        import json
        from unittest.mock import MagicMock, patch

        from libs.pipeline_graph.subgraphs.anchor import _load_registry
        from libs.domain_config.registry import DomainRegistry

        DomainRegistry.reset_instance()

        fake_vs = {
            "resourceType": "ValueSet",
            "id": "ncda-cancer-types",
            "name": "cancer_types",
            "description": "Cancer type concepts",
            "compose": {"include": []},
        }
        mock_kg = MagicMock()
        # First call (episode-detector domains query) returns results
        mock_kg.run.return_value = [
            {"id": "ncda-cancer-types", "raw_json": json.dumps(fake_vs), "domain_id": "cancer_audit"}
        ]

        with patch("libs.neo4j_client.client.KnowledgeGraphClient", return_value=mock_kg):
            registry = _load_registry()
        assert registry is not None

        DomainRegistry.reset_instance()


class TestDomainSummaryModel:
    """VT-084-TC-006: episode_detector field is part of DomainSummary contract."""

    def test_domain_summary_includes_episode_detector(self):
        from services.analytics_api.app.routers.domains import DomainSummary

        d = DomainSummary(
            id="cancer_audit",
            name="Cancer Audit",
            description="",
            episode_detector=True,
        )
        assert d.episode_detector is True

    def test_domain_summary_defaults_episode_detector_to_false(self):
        from services.analytics_api.app.routers.domains import DomainSummary

        d = DomainSummary(id="x", name="X", description="")
        assert d.episode_detector is False

    def test_domain_create_request_episode_detector(self):
        from services.analytics_api.app.routers.domains import DomainCreateRequest

        req = DomainCreateRequest(name="Test", episode_detector=True)
        assert req.episode_detector is True

    def test_domain_update_request_episode_detector_optional(self):
        from services.analytics_api.app.routers.domains import DomainUpdateRequest

        req = DomainUpdateRequest()
        assert req.episode_detector is None

        req2 = DomainUpdateRequest(episode_detector=True)
        assert req2.episode_detector is True


class TestSubdomainAssertionFilterModel:
    """VT-084-TC-007: assertion_filter field is part of SubdomainSummary/SubdomainDetail contract."""

    def test_subdomain_summary_includes_assertion_filter(self):
        from services.analytics_api.app.routers.domains import SubdomainSummary

        s = SubdomainSummary(
            name="cancer_types",
            description="",
            semantic_tags=[],
            assertion_filter=["hypothetical"],
        )
        assert s.assertion_filter == ["hypothetical"]

    def test_subdomain_summary_defaults_assertion_filter_to_empty(self):
        from services.analytics_api.app.routers.domains import SubdomainSummary

        s = SubdomainSummary(name="x", description="", semantic_tags=[])
        assert s.assertion_filter == []

    def test_subdomain_detail_inherits_assertion_filter(self):
        from services.analytics_api.app.routers.domains import SubdomainDetail

        d = SubdomainDetail(
            name="cancer_types",
            description="",
            semantic_tags=[],
            assertion_filter=["present", "hypothetical"],
            concepts=[],
        )
        assert "hypothetical" in d.assertion_filter

    def test_subdomain_update_request_assertion_filter(self):
        from services.analytics_api.app.routers.domains import SubdomainUpdateRequest

        req = SubdomainUpdateRequest(assertion_filter=["hypothetical"])
        assert req.assertion_filter == ["hypothetical"]

    def test_subdomain_update_request_assertion_filter_none_by_default(self):
        from services.analytics_api.app.routers.domains import SubdomainUpdateRequest

        req = SubdomainUpdateRequest()
        assert req.assertion_filter is None


class TestNCDADomainAssertionFilter:
    """Registry dataclass carries assertion_filter field."""

    def test_ncdadomain_has_assertion_filter(self):
        from libs.domain_config.registry import NCDADomain

        d = NCDADomain(
            name="cancer_types",
            file="",
            description="Cancer types",
            milestone_type="diagnosis",
            assertion_filter=["hypothetical"],
        )
        assert d.assertion_filter == ["hypothetical"]

    def test_ncdadomain_default_assertion_filter_empty(self):
        from libs.domain_config.registry import NCDADomain

        d = NCDADomain(name="x", file="", description="")
        assert d.assertion_filter == []

    def test_parse_domain_config_reads_assertion_filter(self):
        from libs.domain_config.registry import DomainRegistry

        vs = {
            "description": "Test",
            "assertionFilter": ["hypothetical", "possible"],
            "extension": [],
        }
        result = DomainRegistry._parse_domain_config(vs, "cancer_types")
        assert result.assertion_filter == ["hypothetical", "possible"]

    def test_parse_domain_config_empty_assertion_filter(self):
        from libs.domain_config.registry import DomainRegistry

        vs = {"description": "Test", "extension": []}
        result = DomainRegistry._parse_domain_config(vs, "cancer_types")
        assert result.assertion_filter == []


class TestStageOfDiagnosisDomainConfig:
    """Stage-of-diagnosis subdomain is available in fallback defaults."""

    def test_stage_of_diagnosis_exists_in_defaults(self):
        from libs.domain_config.registry import NCDA_DOMAIN_CONFIGS

        assert "stage_of_diagnosis" in NCDA_DOMAIN_CONFIGS
        cfg = NCDA_DOMAIN_CONFIGS["stage_of_diagnosis"]
        assert cfg.file == "snomed_ncda_stage_of_diagnosis_mapping.json"
        assert cfg.milestone_type == "diagnosis"
        assert "Tumor_staging" in cfg.semantic_tags
