"""Tests for services/terminology-api/app/services/coding_resolver.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestNormalizeSurface:

    def test_basic_normalization(self):
        from services.terminology_api.app.services.coding_resolver import normalize_surface

        assert normalize_surface("Chest Pain") == "chest pain"
        assert normalize_surface("  Type-2 diabetes!!  ") == "type 2 diabetes"

    def test_empty_string(self):
        from services.terminology_api.app.services.coding_resolver import normalize_surface
        assert normalize_surface("") == ""


class TestEscapeLucene:

    def test_escapes_special_chars(self):
        from services.terminology_api.app.services.coding_resolver import _escape_lucene

        assert "\\" in _escape_lucene("test+query")
        assert "\\" in _escape_lucene("(hello)")


class TestBuildFulltextQueries:

    def test_empty_input(self):
        from services.terminology_api.app.services.coding_resolver import _build_fulltext_queries
        assert _build_fulltext_queries("") == []

    def test_single_word(self):
        from services.terminology_api.app.services.coding_resolver import _build_fulltext_queries
        result = _build_fulltext_queries("cough")
        assert len(result) >= 1

    def test_multi_word_includes_phrase(self):
        from services.terminology_api.app.services.coding_resolver import _build_fulltext_queries
        result = _build_fulltext_queries("chest pain")
        assert any('"' in q for q in result)


class TestCodingCandidate:

    def test_frozen_dataclass(self):
        from services.terminology_api.app.services.coding_resolver import CodingCandidate

        c = CodingCandidate(
            snomed_concept_id="12345",
            snomed_term="Cough",
            read_code="1C1..",
            score=0.95,
            source="hybrid",
        )
        assert c.snomed_concept_id == "12345"
        with pytest.raises(AttributeError):
            c.score = 0.5


class TestCodingResolver:

    def _make_resolver(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver
        return CodingResolver()

    def test_empty_input(self):
        resolver = self._make_resolver()
        result = resolver.resolve_candidates([], neo4j_session=MagicMock())
        assert result == {}

    def test_exact_match_resolves(self):
        resolver = self._make_resolver()
        session = MagicMock()
        session.run.return_value = [
            {
                "concept_id": "49727002",
                "fsn": "Cough (finding)",
                "semantic_tag": "finding",
                "read_codes": ["1C1.."],
                "score": 1.0,
            },
        ]

        result = resolver.resolve_candidates(["cough"], neo4j_session=session)
        assert "cough" in result
        assert len(result["cough"]) >= 1
        assert result["cough"][0].snomed_concept_id == "49727002"

    def test_deduplicates_input(self):
        resolver = self._make_resolver()
        session = MagicMock()
        session.run.return_value = [
            {"concept_id": "12345", "fsn": "Test", "semantic_tag": "finding", "read_codes": [], "score": 1.0},
        ]

        result = resolver.resolve_candidates(["cough", "cough"], neo4j_session=session)
        assert "cough" in result
        assert len(result["cough"]) >= 1

    def test_no_results_returns_empty_lists(self):
        resolver = self._make_resolver()
        session = MagicMock()
        session.run.return_value = []

        result = resolver.resolve_candidates(["unknown_term"], neo4j_session=session)
        assert result["unknown_term"] == []

    def test_tag_boost_applied(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        session = MagicMock()
        session.run.return_value = [
            {"concept_id": "111", "fsn": "Finding A", "semantic_tag": "finding", "read_codes": [], "score": 0.8},
            {"concept_id": "222", "fsn": "Procedure B", "semantic_tag": "procedure", "read_codes": [], "score": 0.85},
        ]

        result = resolver.resolve_candidates(
            ["something"],
            neo4j_session=session,
            expected_tags={"something": "finding"},
        )
        candidates = result["something"]
        if len(candidates) >= 2:
            finding_candidate = next(c for c in candidates if c.snomed_concept_id == "111")
            procedure_candidate = next(c for c in candidates if c.snomed_concept_id == "222")
            assert finding_candidate.score >= procedure_candidate.score
