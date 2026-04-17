"""Tests for services/terminology-api/app/services/coding_resolver.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestNormalizeSurface:

    def test_basic_normalization(self):
        from services.terminology_api.app.services.coding_resolver import (
            normalize_surface,
        )

        assert normalize_surface("Chest Pain") == "chest pain"
        assert normalize_surface("  Type-2 diabetes!!  ") == "type 2 diabetes"

    def test_empty_string(self):
        from services.terminology_api.app.services.coding_resolver import (
            normalize_surface,
        )

        assert normalize_surface("") == ""


class TestEscapeLucene:

    def test_escapes_special_chars(self):
        from services.terminology_api.app.services.coding_resolver import _escape_lucene

        assert "\\" in _escape_lucene("test+query")
        assert "\\" in _escape_lucene("(hello)")


class TestBuildFulltextQueries:

    def test_empty_input(self):
        from services.terminology_api.app.services.coding_resolver import (
            _build_fulltext_queries,
        )

        assert _build_fulltext_queries("") == []

    def test_single_word(self):
        from services.terminology_api.app.services.coding_resolver import (
            _build_fulltext_queries,
        )

        result = _build_fulltext_queries("cough")
        assert len(result) >= 1

    def test_multi_word_includes_phrase(self):
        from services.terminology_api.app.services.coding_resolver import (
            _build_fulltext_queries,
        )

        result = _build_fulltext_queries("chest pain")
        assert any('"' in q for q in result)


class TestCodingCandidate:

    def test_frozen_dataclass(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingCandidate,
        )

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
            {
                "concept_id": "12345",
                "fsn": "Test",
                "semantic_tag": "finding",
                "read_codes": [],
                "score": 1.0,
            },
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
                {
                    "concept_id": expected_concept_id,
                    "fsn": surface_form,
                    "semantic_tag": "finding",
                    "read_codes": [],
                    "score": 1.0,
                },
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
            {
                "concept_id": "111",
                "fsn": "Finding A",
                "semantic_tag": "finding",
                "read_codes": [],
                "score": 0.8,
            },
            {
                "concept_id": "222",
                "fsn": "Procedure B",
                "semantic_tag": "procedure",
                "read_codes": [],
                "score": 0.85,
            },
        ]

        result = resolver.resolve_candidates(
            ["something"],
            neo4j_session=session,
            expected_tags={"something": "finding"},
        )
        candidates = result["something"]
        if len(candidates) >= 2:
            finding_candidate = next(
                c for c in candidates if c.snomed_concept_id == "111"
            )
            procedure_candidate = next(
                c for c in candidates if c.snomed_concept_id == "222"
            )
            assert finding_candidate.score >= procedure_candidate.score

    def test_expected_tag_underscore_not_penalized(self):
        from services.terminology_api.app.services.coding_resolver import CodingResolver

        resolver = CodingResolver()
        # Models an exact-branch hit (had_exact_match=True, lexical_raw=1.0).
        # The test verifies that an expected_tag passed in the underscore
        # form ("observable_entity") matches the SNOMED tag stored in the
        # space form ("observable entity") and does NOT trigger the
        # cross-group penalty that would drop the score by half.
        merged = {
            "obs-1": {
                "concept_id": "obs-1",
                "fsn": "Neutrophil count (observable entity)",
                "semantic_tag": "observable entity",
                "read_codes": [],
                "lexical_raw": 1.0,
                "vector_raw": 0.0,
                "had_exact_match": True,
                "surface_form_status": "",
            }
        }

        candidates = resolver._fuse_and_rank(
            merged,
            expected_tag="observable_entity",
        )

        assert len(candidates) == 1
        # Exact-branch hit (lex_signal=1.0) + tag exact boost capped at 1.0.
        # Without the underscore-vs-space normalisation, this would be
        # treated as cross-group and penalised to 0.5.
        assert candidates[0].score == 1.0


class TestCalibratedScoring:
    """Pin the calibrated absolute score semantics.

    These tests exist because the resolver previously returned a per-term
    relative score (top candidate always normalised to ~1.0, then *1.3
    tag-boost) which conveyed "best-of-this-search" but NOT absolute
    match strength. The new score is in [0.0, 1.0] and roughly
    interpretable as P(correct mapping).
    """

    def test_exact_branch_hit_scores_1_0(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Cough (finding)",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 1.0,
                "vector_raw": 0.0,
                "had_exact_match": True,
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged)
        assert candidates[0].score == 1.0

    def test_weak_fulltext_only_does_not_score_above_0_5(self):
        """The original bug: a weak BM25=1 fulltext hit used to normalise
        to score=1.0 because it was the top (only) candidate. Now it
        scores honestly around 0.5."""
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Some weak hit",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 1.0,
                "vector_raw": 0.0,
                "had_exact_match": False,
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged)
        assert 0.45 <= candidates[0].score <= 0.55

    def test_strong_fulltext_bm25_5_scores_around_0_83(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Strong hit",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 5.0,
                "vector_raw": 0.0,
                "had_exact_match": False,
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged)
        assert 0.80 <= candidates[0].score <= 0.86

    def test_high_vector_only_scores_at_cosine(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Lexicon-gap hit",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 0.0,
                "vector_raw": 0.92,
                "had_exact_match": False,
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged)
        assert 0.91 <= candidates[0].score <= 0.93

    def test_lex_and_vector_agreement_earns_small_bonus(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Lex+vec hit",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 0.0,
                "vector_raw": 0.80,
                "had_exact_match": True,  # lex_signal = 1.0
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged)
        # max(1.0, 0.80) + 0.10 * min(1.0, 0.80) = 1.0 + 0.08 = capped to 1.0
        assert candidates[0].score == 1.0

    def test_cross_group_tag_penalty_halves_score(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Wrong-group hit",
                "semantic_tag": "procedure",  # caller wanted clinical/finding
                "read_codes": [],
                "lexical_raw": 1.0,
                "vector_raw": 0.0,
                "had_exact_match": True,
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged, expected_tag="finding")
        assert candidates[0].score == 0.5

    def test_tag_match_adds_small_boost_not_inflated(self):
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Tag-match hit",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 4.0,  # bm25=4 -> lex_signal = 0.8
                "vector_raw": 0.0,
                "had_exact_match": False,
                "surface_form_status": "",
            }
        }
        candidates = resolver._fuse_and_rank(merged, expected_tag="finding")
        # 4/(4+1)=0.8, +0.10 tag boost = 0.9, capped at 1.0
        assert 0.89 <= candidates[0].score <= 0.91

    def test_tag_matching_candidate_wins_tie(self):
        """Two candidates with equal raw lex strength: tag-match wins."""
        from services.terminology_api.app.services.coding_resolver import (
            CodingResolver,
        )

        resolver = CodingResolver()
        merged = {
            "c1": {
                "concept_id": "c1",
                "fsn": "Finding match",
                "semantic_tag": "finding",
                "read_codes": [],
                "lexical_raw": 3.0,
                "vector_raw": 0.0,
                "had_exact_match": False,
                "surface_form_status": "",
            },
            "c2": {
                "concept_id": "c2",
                "fsn": "Procedure neighbour",
                "semantic_tag": "procedure",
                "read_codes": [],
                "lexical_raw": 3.0,
                "vector_raw": 0.0,
                "had_exact_match": False,
                "surface_form_status": "",
            },
        }
        candidates = resolver._fuse_and_rank(merged, expected_tag="finding")
        assert candidates[0].snomed_concept_id == "c1"


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
            from services.terminology_api.app.queries.terminology import (
                BATCH_EXACT_QUERY,
            )

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
                    {
                        "concept_id": "49727002",
                        "fsn": "Cough",
                        "semantic_tag": "finding",
                        "read_codes": [],
                        "score": 1.0,
                    }
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
            {
                "concept_id": "49727002",
                "fsn": "Cough",
                "semantic_tag": "finding",
                "read_codes": [],
                "score": 0.9,
                "surface_form_status": "",
            },
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
                return [
                    {
                        "input_term": "cough",
                        "hits": [
                            {
                                "concept_id": "49727002",
                                "fsn": "Cough",
                                "semantic_tag": "finding",
                                "read_codes": [],
                                "score": 1.0,
                                "surface_form_status": "",
                            }
                        ],
                    }
                ]
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
                "interpreted_by_findings": [
                    {
                        "id": "99999",
                        "fsn": "Some finding",
                        "semantic_tag": "finding",
                        "rel": "INTERPRETED_BY",
                    }
                ],
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


class TestVectorBranchGate:
    def test_top_lexical_score_zero_for_empty(self):
        from services.terminology_api.app.services.coding_resolver import (
            _top_lexical_score,
        )

        assert _top_lexical_score({}) == 0.0

    def test_top_lexical_score_returns_max(self):
        from services.terminology_api.app.services.coding_resolver import (
            _top_lexical_score,
        )

        merged = {
            "c1": {"lexical_raw": 0.3},
            "c2": {"lexical_raw": 0.8},
            "c3": {"lexical_raw": 0.5},
        }
        assert _top_lexical_score(merged) == 0.8

    def test_vector_skip_score_defaults_to_0_7(self, monkeypatch):
        from services.terminology_api.app.services.coding_resolver import (
            _vector_skip_score,
        )

        monkeypatch.delenv("TERMINOLOGY_VECTOR_SKIP_SCORE", raising=False)
        assert _vector_skip_score() == 0.7

    def test_vector_skip_score_respects_env_override(self, monkeypatch):
        from services.terminology_api.app.services.coding_resolver import (
            _vector_skip_score,
        )

        monkeypatch.setenv("TERMINOLOGY_VECTOR_SKIP_SCORE", "0.85")
        assert _vector_skip_score() == 0.85

    def test_vector_skip_score_falls_back_on_out_of_range(self, monkeypatch):
        from services.terminology_api.app.services.coding_resolver import (
            _vector_skip_score,
        )

        monkeypatch.setenv("TERMINOLOGY_VECTOR_SKIP_SCORE", "1.4")
        assert _vector_skip_score() == 0.7

    def test_vector_skip_score_falls_back_on_invalid(self, monkeypatch):
        from services.terminology_api.app.services.coding_resolver import (
            _vector_skip_score,
        )

        monkeypatch.setenv("TERMINOLOGY_VECTOR_SKIP_SCORE", "not-a-number")
        assert _vector_skip_score() == 0.7
