"""Tests for the Terminology API service layer."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException
from neo4j.exceptions import ServiceUnavailable


class TestCodingResolver:
    """Tests for the hybrid SNOMED coding resolver."""

    def test_resolve_empty_input(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        result = resolver.resolve_candidates([], neo4j_session=MagicMock())
        assert result == {}

    def test_resolve_returns_candidates(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        session = MagicMock()
        session.run.return_value = [
            {
                "concept_id": "25064002",
                "fsn": "Headache (finding)",
                "semantic_tag": "finding",
                "read_codes": ["1BA.."],
                "score": 1.0,
            },
        ]

        resolver = CodingResolver()
        result = resolver.resolve_candidates(["headache"], neo4j_session=session)
        assert "headache" in result
        assert len(result["headache"]) >= 1
        assert result["headache"][0].snomed_concept_id == "25064002"


class TestTerminologyClient:
    """Tests for the shared terminology client parser."""

    def test_parse_results_accepts_current_api_field_names(self):
        from libs.terminology.client import _parse_results

        parsed = _parse_results(
            {
                "haemoptysis": [
                    {
                        "snomed_concept_id": "66857006",
                        "snomed_term": "Haemoptysis",
                        "semantic_tag": "finding",
                        "read_code": "173..",
                        "score": 0.97,
                        "source": "hybrid",
                    }
                ]
            }
        )

        assert "haemoptysis" in parsed
        assert len(parsed["haemoptysis"]) == 1
        assert parsed["haemoptysis"][0].concept_id == "66857006"
        assert parsed["haemoptysis"][0].term == "Haemoptysis"
        assert parsed["haemoptysis"][0].read_code == "173.."


class TestWritebackService:
    """Tests for terminology writeback."""

    def test_extract_surface_form_rows(self):
        from services.terminology_api.app.services.writeback_service import (
            _extract_surface_form_rows,
        )

        sentences_json = json.dumps(
            [
                {
                    "terms": [
                        {
                            "text": "chest pain",
                            "coding": {"snomed_concept_id": "29857009", "score": 0.95},
                        }
                    ],
                }
            ]
        )

        candidates = [{"c": {"sentences_json": sentences_json}, "reviewer": "dr_smith"}]
        rows, stats = _extract_surface_form_rows(candidates)

        assert len(rows) == 1
        assert rows[0]["form"] == "chest pain"
        assert rows[0]["concept_id"] == "29857009"
        assert rows[0]["approved_by"] == "hitl_approved"
        assert stats.eligible == 1

    def test_reviewer_identity_excluded_from_writeback_rows(self):
        """DPA clause 5.3(d): reviewer identity must not reach Knowledge Graph."""
        from services.terminology_api.app.services.writeback_service import (
            _extract_surface_form_rows,
        )

        sentences_json = json.dumps(
            [
                {
                    "terms": [
                        {
                            "text": "raised PSA",
                            "coding": {"snomed_concept_id": "63476009", "score": 0.9},
                        }
                    ],
                }
            ]
        )

        candidates = [
            {"c": {"sentences_json": sentences_json}, "reviewer": "dr.jones@nhs.net"}
        ]
        rows, _ = _extract_surface_form_rows(candidates)

        assert len(rows) == 1
        assert rows[0]["approved_by"] == "hitl_approved"
        assert "dr.jones" not in str(rows[0])
        assert "nhs.net" not in str(rows[0])

    def test_extract_skips_no_concept(self):
        from services.terminology_api.app.services.writeback_service import (
            _extract_surface_form_rows,
        )

        sentences_json = json.dumps(
            [
                {
                    "terms": [{"text": "something", "coding": {}}],
                }
            ]
        )

        candidates = [{"c": {"sentences_json": sentences_json}, "reviewer": "sys"}]
        rows, stats = _extract_surface_form_rows(candidates)

        assert len(rows) == 0
        assert stats.skipped_no_concept == 1


class TestValueSetService:
    """Tests for FHIR ValueSet operations."""

    @patch(
        "services.terminology_api.app.services.valueset_service.KnowledgeGraphClient"
    )
    def test_get_valueset_not_found(self, MockKG):
        from services.terminology_api.app.services.valueset_service import get_valueset

        MockKG.return_value.run.return_value = []
        result = get_valueset("nonexistent")
        assert result is None

    @patch(
        "services.terminology_api.app.services.valueset_service.KnowledgeGraphClient"
    )
    def test_get_valueset_found(self, MockKG):
        from services.terminology_api.app.services.valueset_service import get_valueset

        vs = {"resourceType": "ValueSet", "id": "test-vs"}
        MockKG.return_value.run.return_value = [{"rawJson": json.dumps(vs)}]
        result = get_valueset("test-vs")
        assert result is not None
        assert result["id"] == "test-vs"

    def test_expand_valueset_inline(self):
        from services.terminology_api.app.services.valueset_service import (
            expand_valueset,
        )

        with patch(
            "services.terminology_api.app.services.valueset_service.get_valueset"
        ) as mock_get:
            mock_get.return_value = {
                "resourceType": "ValueSet",
                "id": "test-vs",
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {"code": "12345", "display": "Test concept"},
                                {"code": "67890", "display": "Another concept"},
                            ],
                        }
                    ],
                },
            }

            result = expand_valueset("test-vs")
            assert result is not None
            assert "expansion" in result
            assert result["expansion"]["total"] == 2
            assert result["expansion"]["contains"][0]["code"] == "12345"

    def test_expand_valueset_not_found(self):
        from services.terminology_api.app.services.valueset_service import (
            expand_valueset,
        )

        with patch(
            "services.terminology_api.app.services.valueset_service.get_valueset"
        ) as mock_get:
            mock_get.return_value = None
            result = expand_valueset("missing")
            assert result is None


class TestPriorConceptResolutions:
    """Tests for the concept-mapping nudge's prior-resolution lookup."""

    @patch(
        "services.terminology_api.app.services.prior_resolutions.KnowledgeGraphClient"
    )
    def test_empty_term_short_circuits_without_a_query(self, MockKG):
        from services.terminology_api.app.services.prior_resolutions import (
            find_prior_concept_resolutions,
        )

        result = find_prior_concept_resolutions("   ")
        assert result == []
        MockKG.assert_not_called()

    @patch(
        "services.terminology_api.app.services.prior_resolutions.KnowledgeGraphClient"
    )
    def test_ranks_by_frequency_across_rules(self, MockKG):
        from services.terminology_api.app.services.prior_resolutions import (
            find_prior_concept_resolutions,
        )

        MockKG.return_value.run.return_value = [
            {
                "rule_id": "rule-1",
                "logic_json": json.dumps(
                    {
                        "kind": "concept",
                        "criterion": {
                            "snomed_concept_id": "422587007",
                            "term": "vomiting",
                            "preferred_term": "Vomiting (finding)",
                        },
                    }
                ),
            },
            {
                "rule_id": "rule-2",
                "logic_json": json.dumps(
                    {
                        "kind": "AND",
                        "children": [
                            {
                                "kind": "concept",
                                "criterion": {
                                    "snomed_concept_id": "422587007",
                                    "preferred_term": "Vomiting (finding)",
                                },
                            },
                            {
                                "kind": "concept",
                                "criterion": {
                                    "snomed_concept_id": "999999999",
                                    "term": "vomiting",
                                    "preferred_term": "A different vomiting (finding)",
                                },
                            },
                        ],
                    }
                ),
            },
        ]

        result = find_prior_concept_resolutions("Vomiting")
        assert result[0]["snomed_concept_id"] == "422587007"
        assert result[0]["count"] == 2
        assert result[1]["snomed_concept_id"] == "999999999"
        assert result[1]["count"] == 1

    @patch(
        "services.terminology_api.app.services.prior_resolutions.KnowledgeGraphClient"
    )
    def test_ignores_rules_where_term_only_matches_a_different_criterion(self, MockKG):
        from services.terminology_api.app.services.prior_resolutions import (
            find_prior_concept_resolutions,
        )

        # A CONTAINS pre-filter hit whose actual concept criteria never
        # mention "vomiting" (e.g. it appears inside an unrelated field)
        # must not be counted -- the Python walker re-checks the exact
        # normalised term before accumulating a hit.
        MockKG.return_value.run.return_value = [
            {
                "rule_id": "rule-3",
                "logic_json": json.dumps(
                    {
                        "kind": "concept",
                        "criterion": {
                            "snomed_concept_id": "1",
                            "preferred_term": "Nausea (finding)",
                        },
                    }
                ),
            }
        ]

        assert find_prior_concept_resolutions("vomiting") == []

    @patch(
        "services.terminology_api.app.services.prior_resolutions.KnowledgeGraphClient"
    )
    def test_respects_limit(self, MockKG):
        from services.terminology_api.app.services.prior_resolutions import (
            find_prior_concept_resolutions,
        )

        MockKG.return_value.run.return_value = [
            {
                "rule_id": f"rule-{i}",
                "logic_json": json.dumps(
                    {
                        "kind": "concept",
                        "criterion": {
                            "snomed_concept_id": str(i),
                            "term": "vomiting",
                            "preferred_term": f"Vomiting variant {i}",
                        },
                    }
                ),
            }
            for i in range(10)
        ]

        result = find_prior_concept_resolutions("vomiting", limit=3)
        assert len(result) == 3


class TestResolveRouterRetry:
    """Tests for retry behaviour in terminology resolve router."""

    @staticmethod
    @contextmanager
    def _session_cm():
        yield MagicMock()

    def test_resolve_retries_transient_neo4j_error(self, monkeypatch):
        from services.terminology_api.app.routers import resolve as resolve_router

        monkeypatch.setattr(
            resolve_router._kg_client,
            "session",
            lambda: self._session_cm(),
        )

        call_count = {"n": 0}

        def _resolve(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ServiceUnavailable("simulated transient outage")
            return {"cough": []}

        monkeypatch.setattr(resolve_router._resolver, "resolve_candidates", _resolve)

        body = resolve_router.ResolveRequest(terms=["cough"])
        resp = resolve_router.resolve_terms(body)
        assert "cough" in resp.results
        assert call_count["n"] == 2

    def test_resolve_returns_503_after_retries_exhausted(self, monkeypatch):
        from services.terminology_api.app.routers import resolve as resolve_router

        monkeypatch.setattr(
            resolve_router._kg_client,
            "session",
            lambda: self._session_cm(),
        )

        def _always_fail(*args, **kwargs):
            raise ServiceUnavailable("persistent outage")

        monkeypatch.setattr(
            resolve_router._resolver, "resolve_candidates", _always_fail
        )

        body = resolve_router.ResolveRequest(terms=["cough"])
        with pytest.raises(HTTPException) as exc_info:
            resolve_router.resolve_terms(body)
        assert exc_info.value.status_code == 503
