"""Tests for V3 coding resolver."""

from __future__ import annotations

from unittest.mock import MagicMock

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

    def test_resolve_returns_candidates_from_session(self) -> None:
        resolver = CodingResolver()
        session = MagicMock()
        session.run.return_value = [
            {
                "normalized": "hypertension",
                "snomed_concept_id": "38341003",
                "snomed_term": "Hypertensive disorder",
                "read_code": "G20",
            },
        ]
        result = resolver.resolve_candidates(["hypertension"], neo4j_session=session)
        assert "hypertension" in result
        assert len(result["hypertension"]) == 1
        assert result["hypertension"][0].snomed_concept_id == "38341003"
        assert result["hypertension"][0].read_code == "G20"
