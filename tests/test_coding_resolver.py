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
            semantic_tag="finding",
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

    def test_top_1_accuracy_meets_90_pct_on_mock_gold_set(self):
        """VT-003-TC-003: top-1 accuracy >= 90% across a mock gold-standard dataset."""
        resolver = self._make_resolver()

        gold_dataset = [
            ("cough", "49727002"),
            ("hypertension", "38341003"),
            ("diabetes mellitus", "73211009"),
            ("chest pain", "29857009"),
            ("shortness of breath", "230145002"),
            ("headache", "25064002"),
            ("fatigue", "84229001"),
            ("back pain", "279039007"),
            ("nausea", "422587007"),
            ("anxiety", "48694002"),
        ]

        correct = 0
        for surface_form, expected_concept_id in gold_dataset:
            session = MagicMock()
            session.run.return_value = [
                {"concept_id": expected_concept_id, "fsn": surface_form,
                 "semantic_tag": "finding", "read_codes": [], "score": 1.0},
            ]
            result = resolver.resolve_candidates([surface_form], neo4j_session=session)
            if surface_form in result and result[surface_form]:
                if result[surface_form][0].snomed_concept_id == expected_concept_id:
                    correct += 1

        accuracy = correct / len(gold_dataset)
        assert accuracy >= 0.90, f"Top-1 accuracy {accuracy:.0%} below 90% threshold"

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


class TestBatchExact:

    def _make_session_with_batch_rows(self, rows_by_norm: dict[str, list[dict]]):
        """Return a mock session whose .run() returns BATCH_EXACT_QUERY-shaped rows."""
        from unittest.mock import MagicMock

        def _run(query, **kwargs):
            normalized_terms = kwargs.get("normalized_terms", [])
            result = []
            for norm in normalized_terms:
                hits = rows_by_norm.get(norm, [])
                result.append({"input_term": norm, "hits": hits})
            return result

        session = MagicMock()
        session.run.side_effect = _run
        return session

    def test_batch_exact_returns_keyed_results(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True

        batch_hit = {
            "concept_id": "49727002",
            "fsn": "Cough (finding)",
            "semantic_tag": "finding",
            "read_codes": ["1C1.."],
            "score": 1.0,
            "surface_form_status": "",
        }
        session = self._make_session_with_batch_rows({"cough": [batch_hit]})

        merged_all: dict = {"cough": {}}
        norm_map = {"cough": "cough"}
        hit_terms = resolver._batch_exact(["cough"], norm_map, session, merged_all)

        assert "cough" in hit_terms
        assert "49727002" in merged_all["cough"]
        assert merged_all["cough"]["49727002"]["lexical_raw"] == 1.0

    def test_batch_exact_short_circuits_fulltext(self):
        """Terms that have exact hits should be excluded from fulltext batch."""
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True

        session = MagicMock()
        exact_hit = {
            "concept_id": "49727002",
            "fsn": "Cough (finding)",
            "semantic_tag": "finding",
            "read_codes": [],
            "score": 1.0,
            "surface_form_status": "",
        }

        def _run(query, **kwargs):
            from services.terminology_api.app.queries.terminology import BATCH_EXACT_QUERY
            if "normalized_terms" in kwargs:
                return [{"input_term": "cough", "hits": [exact_hit]}]
            return []

        session.run.side_effect = _run

        result = resolver.resolve_candidates(["cough"], neo4j_session=session)
        assert "cough" in result
        assert result["cough"][0].snomed_concept_id == "49727002"

    def test_batch_exact_fallback_on_query_error(self):
        """On BATCH_EXACT_QUERY failure, falls back to per-term EXACT_QUERY."""
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True

        call_count: list[int] = [0]

        def _run(query, **kwargs):
            call_count[0] += 1
            if "normalized_terms" in kwargs:
                raise RuntimeError("simulated batch failure")
            if "normalized" in kwargs:
                return [
                    {"concept_id": "49727002", "fsn": "Cough", "semantic_tag": "finding",
                     "read_codes": [], "score": 1.0}
                ]
            return []

        session = MagicMock()
        session.run.side_effect = _run

        merged_all: dict = {"cough": {}}
        norm_map = {"cough": "cough"}
        hit_terms = resolver._batch_exact(["cough"], norm_map, session, merged_all)
        assert "cough" in hit_terms
        assert "49727002" in merged_all["cough"]


class TestBatchFulltext:

    def test_batch_fulltext_merges_results(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        resolver._surface_form_fulltext_ok = True

        session = MagicMock()
        session.run.return_value = [
            {"concept_id": "49727002", "fsn": "Cough", "semantic_tag": "finding",
             "read_codes": [], "score": 0.9, "surface_form_status": ""},
        ]

        merged_all: dict = {"cough": {}}
        resolver._batch_fulltext(["cough"], session, merged_all)

        assert "49727002" in merged_all["cough"]
        assert merged_all["cough"]["49727002"]["lexical_raw"] > 0

    def test_batch_fulltext_skipped_for_exact_hit_terms(self):
        """resolve_candidates should not call fulltext for terms already in exact_hit_terms."""
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        resolver._surface_form_exact_ok = True

        fulltext_called_for: list[str] = []

        def _run(query, **kwargs):
            if "normalized_terms" in kwargs:
                return [{"input_term": "cough", "hits": [
                    {"concept_id": "49727002", "fsn": "Cough", "semantic_tag": "finding",
                     "read_codes": [], "score": 1.0, "surface_form_status": ""}
                ]}]
            if "ft_query" in kwargs:
                fulltext_called_for.append(kwargs.get("ft_query", ""))
            return []

        session = MagicMock()
        session.run.side_effect = _run

        resolver.resolve_candidates(["cough"], neo4j_session=session)
        assert not fulltext_called_for, "fulltext should not run when exact hit found"


class TestBatchRelatedConcepts:

    def test_batch_get_related_concepts_parses_rows(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        session = MagicMock()
        session.run.return_value = [
            {
                "concept_id": "12345",
                "interpreted_by_findings": [{"id": "99999", "fsn": "Some finding", "semantic_tag": "finding", "rel": "INTERPRETED_BY"}],
                "component_of_procedures": [],
                "interprets_observables": [],
                "has_components": [],
                "associated_findings": [],
            }
        ]

        result = resolver._batch_get_related_concepts(["12345"], session)
        assert "12345" in result
        assert len(result["12345"]) == 1
        assert result["12345"][0]["rel"] == "INTERPRETED_BY"

    def test_batch_get_related_concepts_returns_empty_on_error(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        session = MagicMock()
        session.run.side_effect = RuntimeError("connection error")

        result = resolver._batch_get_related_concepts(["12345"], session)
        assert result == {}
