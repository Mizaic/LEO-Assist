"""Tests for V3 hybrid coding resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.services.v3.coding_resolver import CodingResolver


class TestCodingResolver:
    """Test candidate resolution."""

    def test_resolve_empty_returns_empty(self) -> None:
        resolver = CodingResolver()
        session = MagicMock()
        result = resolver.resolve_candidates([], neo4j_session=session)
        assert result == {}
        session.run.assert_not_called()

    def test_resolve_exact_hit(self) -> None:
        resolver = CodingResolver()
        session = MagicMock()

        exact_row = {
            "concept_id": "38341003",
            "fsn": "Hypertensive disorder",
            "semantic_tag": "disorder",
            "read_codes": ["G20"],
            "score": 1.0,
        }
        session.run.side_effect = [
            [exact_row],   # exact query
            [],            # SurfaceForm probe (not present)
            [],            # fulltext query 1
            [],            # fulltext query 2
        ]
        result = resolver.resolve_candidates(["hypertension"], neo4j_session=session)

        assert "hypertension" in result
        assert len(result["hypertension"]) >= 1
        assert result["hypertension"][0].snomed_concept_id == "38341003"
        assert result["hypertension"][0].read_code == "G20"

    def test_resolve_fulltext_hit_when_no_exact(self) -> None:
        resolver = CodingResolver()
        session = MagicMock()

        fulltext_row = {
            "concept_id": "12345",
            "fsn": "Left shoulder pain (finding)",
            "semantic_tag": "finding",
            "read_codes": [],
            "score": 4.5,
        }
        session.run.side_effect = [
            [],               # exact query — no match
            [],               # SurfaceForm probe (not present)
            [fulltext_row],   # fulltext query 1
            [],               # fulltext query 2
        ]
        result = resolver.resolve_candidates(["left shoulder pain"], neo4j_session=session)

        assert "left shoulder pain" in result
        assert len(result["left shoulder pain"]) >= 1
        assert result["left shoulder pain"][0].snomed_concept_id == "12345"

    def test_resolve_merges_exact_and_fulltext(self) -> None:
        resolver = CodingResolver()
        session = MagicMock()

        exact_row = {
            "concept_id": "AAA",
            "fsn": "Exact match",
            "semantic_tag": "disorder",
            "read_codes": [],
            "score": 1.0,
        }
        fulltext_row = {
            "concept_id": "BBB",
            "fsn": "Fulltext match",
            "semantic_tag": "finding",
            "read_codes": [],
            "score": 3.0,
        }
        session.run.side_effect = [
            [exact_row],        # exact
            [],                 # SurfaceForm probe (not present)
            [fulltext_row],     # fulltext 1
            [],                 # fulltext 2
        ]
        result = resolver.resolve_candidates(["test term"], neo4j_session=session)

        assert "test term" in result
        assert len(result["test term"]) == 2
        concept_ids = {c.snomed_concept_id for c in result["test term"]}
        assert concept_ids == {"AAA", "BBB"}

    def test_resolve_deduplicates_same_concept(self) -> None:
        resolver = CodingResolver()
        session = MagicMock()

        row = {
            "concept_id": "38341003",
            "fsn": "Hypertensive disorder",
            "semantic_tag": "disorder",
            "read_codes": ["G20"],
            "score": 1.0,
        }
        session.run.side_effect = [
            [row],  # exact
            [],     # SurfaceForm probe (not present)
            [row],  # fulltext 1 — same concept
            [],     # fulltext 2
        ]
        result = resolver.resolve_candidates(["hypertension"], neo4j_session=session)

        assert len(result["hypertension"]) == 1
