"""Tests for V3 disambiguator."""

from __future__ import annotations

import pytest

from app.services.v3.coding_resolver import CodingCandidate
from app.services.v3.disambiguator import CodingDisambiguator


class TestCodingDisambiguator:
    """Test disambiguation logic."""

    def test_choose_best_empty_candidates_returns_none(self) -> None:
        disambiguator = CodingDisambiguator(model_id="unconfigured", region=None)
        result = disambiguator.choose_best(
            encounter_text="Patient has diabetes.",
            term_text="diabetes",
            candidates=[],
        )
        assert result is None

    def test_choose_best_single_candidate_returns_it(self) -> None:
        disambiguator = CodingDisambiguator(model_id="unconfigured", region=None)
        candidate = CodingCandidate(
            snomed_concept_id="73211009",
            snomed_term="Diabetes mellitus",
            read_code="C10",
            score=1.0,
            source="neo4j_hybrid",
        )
        result = disambiguator.choose_best(
            encounter_text="Patient has diabetes.",
            term_text="diabetes",
            candidates=[candidate],
        )
        assert result is not None
        assert result.snomed_concept_id == "73211009"

    def test_choose_best_disabled_returns_first_when_multiple(self) -> None:
        disambiguator = CodingDisambiguator(model_id="unconfigured", region=None)
        c1 = CodingCandidate("111", "Term A", "R1", 1.0, "neo4j")
        c2 = CodingCandidate("222", "Term B", "R2", 1.0, "neo4j")
        result = disambiguator.choose_best(
            encounter_text="Patient has condition.",
            term_text="condition",
            candidates=[c1, c2],
        )
        assert result is not None
        assert result.snomed_concept_id == "111"
