"""Tests for the Terminology API service layer."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestCodingResolver:
    """Tests for the hybrid SNOMED coding resolver."""

    @patch("libs.neo4j_client.client.KnowledgeGraphClient")
    def test_exact_match_returns_first(self, MockKG):
        from services.terminology_api.app.services.coding_resolver import resolve_term

        instance = MockKG.return_value
        instance.run.side_effect = [
            [{"conceptId": "12345", "term": "Headache", "semanticTag": "finding", "readCode": "1BA.."}],
            [],
            [],
        ]

        results = resolve_term("headache", limit=5)
        assert len(results) >= 1
        assert results[0]["conceptId"] == "12345"

    @patch("libs.neo4j_client.client.KnowledgeGraphClient")
    def test_empty_query_returns_empty(self, MockKG):
        from services.terminology_api.app.services.coding_resolver import resolve_term

        instance = MockKG.return_value
        instance.run.return_value = []

        results = resolve_term("", limit=5)
        assert results == []


class TestWritebackService:
    """Tests for terminology writeback."""

    @patch("libs.neo4j_client.client.KnowledgeGraphClient")
    @patch("libs.neo4j_client.client.PatientGraphClient")
    def test_upsert_surface_form_calls_kg(self, MockPG, MockKG):
        from services.terminology_api.app.services.writeback_service import upsert_surface_form

        kg = MockKG.return_value
        kg.run.return_value = []

        upsert_surface_form(
            surface_form="chest pain",
            concept_id="29857009",
            source="hitl_review",
        )
        kg.run.assert_called()


class TestValueSetService:
    """Tests for FHIR ValueSet operations."""

    @patch("libs.neo4j_client.client.KnowledgeGraphClient")
    def test_get_valueset_not_found(self, MockKG):
        from services.terminology_api.app.services.valueset_service import get_valueset

        instance = MockKG.return_value
        instance.run.return_value = []

        result = get_valueset("nonexistent")
        assert result is None

    @patch("libs.neo4j_client.client.KnowledgeGraphClient")
    def test_expand_valueset_returns_concepts(self, MockKG):
        import json
        from services.terminology_api.app.services.valueset_service import expand_valueset

        instance = MockKG.return_value
        instance.run.side_effect = [
            [{"rawJson": json.dumps({"resourceType": "ValueSet", "id": "test-vs", "compose": {"include": [{"system": "http://snomed.info/sct"}]}})}],
            [{"code": "12345", "display": "Test concept", "system": "http://snomed.info/sct"}],
        ]

        result = expand_valueset("test-vs")
        assert result is not None
        assert result["resourceType"] == "ValueSet"
