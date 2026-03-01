"""Tests for the FHIR API service layer."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


class TestMeasureService:
    """Tests for FHIR Measure CRUD and evaluation."""

    @patch("services.fhir_api.app.services.measure_service.KnowledgeGraphClient")
    def test_get_measure_found(self, MockKG):
        from services.fhir_api.app.services.measure_service import get_measure

        measure = {"resourceType": "Measure", "id": "test-m", "name": "Test"}
        MockKG.return_value.run.return_value = [{"rawJson": json.dumps(measure)}]

        result = get_measure("test-m")
        assert result is not None
        assert result["id"] == "test-m"

    @patch("services.fhir_api.app.services.measure_service.KnowledgeGraphClient")
    def test_get_measure_not_found(self, MockKG):
        from services.fhir_api.app.services.measure_service import get_measure

        MockKG.return_value.run.return_value = []
        result = get_measure("nonexistent")
        assert result is None

    @patch("services.fhir_api.app.services.measure_service.KnowledgeGraphClient")
    def test_upsert_measure(self, MockKG):
        from services.fhir_api.app.services.measure_service import upsert_measure

        resource = {"resourceType": "Measure", "id": "test-m", "name": "Test", "status": "active"}
        result = upsert_measure("test-m", resource)
        assert result["id"] == "test-m"
        MockKG.return_value.run.assert_called_once()

    @patch("services.fhir_api.app.services.measure_service.KnowledgeGraphClient")
    def test_delete_measure(self, MockKG):
        from services.fhir_api.app.services.measure_service import delete_measure

        delete_measure("test-m")
        MockKG.return_value.run.assert_called_once()


class TestLibraryService:
    """Tests for FHIR Library CRUD."""

    @patch("services.fhir_api.app.services.library_service.KnowledgeGraphClient")
    def test_get_library_found(self, MockKG):
        from services.fhir_api.app.services.library_service import get_library

        library = {"resourceType": "Library", "id": "test-lib", "name": "Test Query"}
        MockKG.return_value.run.return_value = [{"rawJson": json.dumps(library)}]

        result = get_library("test-lib")
        assert result is not None
        assert result["id"] == "test-lib"

    @patch("services.fhir_api.app.services.library_service.KnowledgeGraphClient")
    def test_get_library_not_found(self, MockKG):
        from services.fhir_api.app.services.library_service import get_library

        MockKG.return_value.run.return_value = []
        result = get_library("nonexistent")
        assert result is None
