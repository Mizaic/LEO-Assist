"""Tests for FHIR Measure evaluation and extract_cypher_and_hash."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch, MagicMock

import pytest


class TestExtractCypherAndHash:

    def test_extracts_cypher_from_library(self):
        from services.fhir_api.app.services.measure_service import extract_cypher_and_hash

        cypher_b64 = base64.b64encode(b"MATCH (n) RETURN n LIMIT 10").decode()
        hash_b64 = base64.b64encode(b"abc123hash").decode()

        library = {
            "content": [
                {"title": "cypher", "data": cypher_b64},
                {"title": "cypher-sha256", "data": hash_b64},
            ]
        }

        cypher, cypher_hash = extract_cypher_and_hash(library)
        assert cypher == "MATCH (n) RETURN n LIMIT 10"
        assert cypher_hash == "abc123hash"

    def test_empty_content(self):
        from services.fhir_api.app.services.measure_service import extract_cypher_and_hash

        cypher, cypher_hash = extract_cypher_and_hash({"content": []})
        assert cypher == ""
        assert cypher_hash == ""

    def test_no_content_key(self):
        from services.fhir_api.app.services.measure_service import extract_cypher_and_hash

        cypher, cypher_hash = extract_cypher_and_hash({})
        assert cypher == ""
        assert cypher_hash == ""

    def test_only_cypher_no_hash(self):
        from services.fhir_api.app.services.measure_service import extract_cypher_and_hash

        cypher_b64 = base64.b64encode(b"RETURN 1").decode()
        library = {"content": [{"title": "cypher", "data": cypher_b64}]}

        cypher, cypher_hash = extract_cypher_and_hash(library)
        assert cypher == "RETURN 1"
        assert cypher_hash == ""


class TestEvaluateMeasure:

    @patch("services.fhir_api.app.services.measure_service.PatientGraphClient")
    @patch("services.fhir_api.app.services.measure_service._get_library")
    @patch("services.fhir_api.app.services.measure_service.get_measure")
    def test_successful_evaluation(self, mock_get_measure, mock_get_lib, MockPG):
        from services.fhir_api.app.services.measure_service import evaluate_measure

        mock_get_measure.return_value = {
            "resourceType": "Measure",
            "id": "m-1",
            "library": ["Library/lib-1"],
        }

        cypher_b64 = base64.b64encode(b"MATCH (n) WHERE n.org = $org RETURN count(n) AS cnt").decode()
        mock_get_lib.return_value = {
            "content": [{"title": "cypher", "data": cypher_b64}],
        }

        MockPG.return_value.run.return_value = [{"cnt": 42}]

        result = evaluate_measure("m-1", {"org": "ORG-1"})
        assert result["resourceType"] == "MeasureReport"
        assert result["status"] == "complete"
        MockPG.return_value.close.assert_called_once()

    @patch("services.fhir_api.app.services.measure_service.get_measure")
    def test_measure_not_found(self, mock_get_measure):
        from services.fhir_api.app.services.measure_service import evaluate_measure

        mock_get_measure.return_value = None
        result = evaluate_measure("m-999", {})
        assert "error" in result

    @patch("services.fhir_api.app.services.measure_service.get_measure")
    def test_no_library_reference(self, mock_get_measure):
        from services.fhir_api.app.services.measure_service import evaluate_measure

        mock_get_measure.return_value = {"id": "m-1", "library": []}
        result = evaluate_measure("m-1", {})
        assert "error" in result
        assert "library" in result["error"].lower()

    @patch("services.fhir_api.app.services.measure_service._get_library")
    @patch("services.fhir_api.app.services.measure_service.get_measure")
    def test_library_not_found(self, mock_get_measure, mock_get_lib):
        from services.fhir_api.app.services.measure_service import evaluate_measure

        mock_get_measure.return_value = {"id": "m-1", "library": ["Library/lib-99"]}
        mock_get_lib.return_value = None
        result = evaluate_measure("m-1", {})
        assert "error" in result

    @patch("services.fhir_api.app.services.measure_service._get_library")
    @patch("services.fhir_api.app.services.measure_service.get_measure")
    def test_no_cypher_in_library(self, mock_get_measure, mock_get_lib):
        from services.fhir_api.app.services.measure_service import evaluate_measure

        mock_get_measure.return_value = {"id": "m-1", "library": ["Library/lib-1"]}
        mock_get_lib.return_value = {"content": []}
        result = evaluate_measure("m-1", {})
        assert "error" in result
        assert "cypher" in result["error"].lower()


class TestSearchMeasures:

    @patch("services.fhir_api.app.services.measure_service.KnowledgeGraphClient")
    def test_returns_items_and_total(self, MockKG):
        from services.fhir_api.app.services.measure_service import search_measures

        measure = {"id": "m-1", "name": "Test"}
        MockKG.return_value.run.side_effect = [
            [{"total": 1}],
            [{"rawJson": json.dumps(measure)}],
        ]

        items, total = search_measures(name="Test")
        assert total == 1
        assert len(items) == 1

    @patch("services.fhir_api.app.services.measure_service.KnowledgeGraphClient")
    def test_empty_result(self, MockKG):
        from services.fhir_api.app.services.measure_service import search_measures

        MockKG.return_value.run.side_effect = [
            [{"total": 0}],
            [],
        ]

        items, total = search_measures()
        assert total == 0
        assert items == []


class TestBuildMeasureReport:

    def test_report_structure(self):
        from services.fhir_api.app.services.measure_service import _build_measure_report

        measure = {"id": "m-1", "name": "Test"}
        results = [{"condition_type": "breast", "count": 10}]

        report = _build_measure_report("m-1", measure, results)
        assert report["resourceType"] == "MeasureReport"
        assert report["type"] == "summary"
        assert report["measure"] == "Measure/m-1"
        assert len(report["extension"]) == 1
        data = json.loads(report["extension"][0]["valueString"])
        assert data[0]["condition_type"] == "breast"
