"""Tests for services/terminology-api/app/services/conceptmap_service.py."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


class TestFirst:

    def test_empty_list_returns_none(self):
        from services.terminology_api.app.services.conceptmap_service import _first

        assert _first([]) is None

    def test_parses_rawjson(self):
        from services.terminology_api.app.services.conceptmap_service import _first

        result = _first([{"rawJson": '{"id": "cm-1"}'}])
        assert result == {"id": "cm-1"}

    def test_missing_rawjson_returns_none(self):
        from services.terminology_api.app.services.conceptmap_service import _first

        assert _first([{"rawJson": None}]) is None
        assert _first([{}]) is None


class TestUpsertConceptMap:

    @patch(
        "services.terminology_api.app.services.conceptmap_service.KnowledgeGraphClient"
    )
    def test_upsert_returns_resource(self, MockKG):
        from services.terminology_api.app.services.conceptmap_service import (
            upsert_conceptmap,
        )

        resource = {
            "url": "http://ex.org/cm",
            "name": "Test",
            "title": "Test CM",
            "status": "active",
        }
        MockKG.return_value.run.return_value = [{"rawJson": json.dumps(resource)}]

        result = upsert_conceptmap("cm-1", resource)
        assert result is not None
        assert result["name"] == "Test"
        MockKG.return_value.close.assert_called_once()


class TestGetConceptMap:

    @patch(
        "services.terminology_api.app.services.conceptmap_service.KnowledgeGraphClient"
    )
    def test_found(self, MockKG):
        from services.terminology_api.app.services.conceptmap_service import (
            get_conceptmap,
        )

        cm = {"resourceType": "ConceptMap", "id": "cm-1"}
        MockKG.return_value.run.return_value = [{"rawJson": json.dumps(cm)}]

        result = get_conceptmap("cm-1")
        assert result["id"] == "cm-1"

    @patch(
        "services.terminology_api.app.services.conceptmap_service.KnowledgeGraphClient"
    )
    def test_not_found(self, MockKG):
        from services.terminology_api.app.services.conceptmap_service import (
            get_conceptmap,
        )

        MockKG.return_value.run.return_value = []
        assert get_conceptmap("nonexistent") is None


class TestDeleteConceptMap:

    @patch(
        "services.terminology_api.app.services.conceptmap_service.KnowledgeGraphClient"
    )
    def test_calls_delete(self, MockKG):
        from services.terminology_api.app.services.conceptmap_service import (
            delete_conceptmap,
        )

        delete_conceptmap("cm-1")
        MockKG.return_value.run.assert_called_once()
        MockKG.return_value.close.assert_called_once()


class TestSearchConceptMaps:

    @patch(
        "services.terminology_api.app.services.conceptmap_service.KnowledgeGraphClient"
    )
    def test_returns_items_and_total(self, MockKG):
        from services.terminology_api.app.services.conceptmap_service import (
            search_conceptmaps,
        )

        cm = {"id": "cm-1", "name": "Test"}
        MockKG.return_value.run.side_effect = [
            [{"total": 1}],
            [{"rawJson": json.dumps(cm)}],
        ]

        items, total = search_conceptmaps(name="Test")
        assert total == 1
        assert len(items) == 1
        assert items[0]["name"] == "Test"


class TestTranslateConcept:

    @patch("services.terminology_api.app.services.conceptmap_service.get_conceptmap")
    def test_translate_found(self, mock_get):
        from services.terminology_api.app.services.conceptmap_service import (
            translate_concept,
        )

        mock_get.return_value = {
            "group": [
                {
                    "source": "http://snomed.info/sct",
                    "target": "http://read.info",
                    "element": [
                        {
                            "code": "12345",
                            "target": [
                                {
                                    "code": "ABC",
                                    "display": "Test Code",
                                    "equivalence": "equivalent",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        result = translate_concept("cm-1", "12345")
        assert result is not None
        assert result["parameter"][0]["valueBoolean"] is True
        assert len(result["parameter"]) == 2

    @patch("services.terminology_api.app.services.conceptmap_service.get_conceptmap")
    def test_translate_not_found(self, mock_get):
        from services.terminology_api.app.services.conceptmap_service import (
            translate_concept,
        )

        mock_get.return_value = None
        result = translate_concept("cm-1", "12345")
        assert result is None

    @patch("services.terminology_api.app.services.conceptmap_service.get_conceptmap")
    def test_translate_no_match(self, mock_get):
        from services.terminology_api.app.services.conceptmap_service import (
            translate_concept,
        )

        mock_get.return_value = {
            "group": [
                {
                    "source": "http://snomed.info/sct",
                    "target": "http://read.info",
                    "element": [{"code": "99999", "target": []}],
                }
            ],
        }

        result = translate_concept("cm-1", "12345")
        assert result["parameter"][0]["valueBoolean"] is False

    @patch("services.terminology_api.app.services.conceptmap_service.get_conceptmap")
    def test_translate_filters_by_system(self, mock_get):
        from services.terminology_api.app.services.conceptmap_service import (
            translate_concept,
        )

        mock_get.return_value = {
            "group": [
                {
                    "source": "http://read.info",
                    "target": "http://snomed.info/sct",
                    "element": [
                        {"code": "12345", "target": [{"code": "X", "display": "Wrong"}]}
                    ],
                },
                {
                    "source": "http://snomed.info/sct",
                    "target": "http://read.info",
                    "element": [
                        {"code": "12345", "target": [{"code": "Y", "display": "Right"}]}
                    ],
                },
            ],
        }

        result = translate_concept("cm-1", "12345", system="http://snomed.info/sct")
        matches = [p for p in result["parameter"] if p.get("name") == "match"]
        assert len(matches) == 1
        concept = matches[0]["part"][1]["valueCoding"]
        assert concept["code"] == "Y"
