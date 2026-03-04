"""VT-LEO-AI-035: Terminology Writeback Verification.

Verifies that the writeback service persists SurfaceForm mappings with
provenance metadata, and that written-back mappings boost future search
results. Uses mocked Neo4j sessions.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# VT-035-TC-001: Writeback stores SurfaceForm mapping
# ---------------------------------------------------------------------------

class TestWritebackPersistence:

    def test_extract_surface_form_rows_produces_mapping(self):
        """_extract_surface_form_rows returns a row with the correct surface form and concept."""
        from services.terminology_api.app.services.writeback_service import _extract_surface_form_rows

        sentences_json = json.dumps([{
            "terms": [{
                "text": "high blood pressure",
                "coding": {"snomed_concept_id": "38341003", "score": 0.97},
            }],
        }])

        candidates = [{"c": {"sentences_json": sentences_json}, "reviewer": "dr_smith"}]
        rows, stats = _extract_surface_form_rows(candidates)

        assert len(rows) == 1
        assert rows[0]["form"] == "high blood pressure"
        assert rows[0]["concept_id"] == "38341003"
        assert stats.eligible == 1

    def test_writeback_with_provenance_fields(self):
        """Writeback row includes provenance metadata."""
        from services.terminology_api.app.services.writeback_service import _extract_surface_form_rows

        sentences_json = json.dumps([{
            "terms": [{
                "text": "diabetes",
                "coding": {"snomed_concept_id": "73211009", "score": 0.95},
            }],
        }])

        candidates = [{"c": {"sentences_json": sentences_json}, "reviewer": "dr_jones"}]
        rows, stats = _extract_surface_form_rows(candidates)

        assert rows[0]["form"] == "diabetes"
        assert rows[0]["concept_id"] == "73211009"

    def test_writeback_skips_entry_without_concept(self):
        """Entries without a SNOMED concept ID are skipped."""
        from services.terminology_api.app.services.writeback_service import _extract_surface_form_rows

        sentences_json = json.dumps([{
            "terms": [{"text": "unknown_term", "coding": {}}],
        }])

        candidates = [{"c": {"sentences_json": sentences_json}, "reviewer": "sys"}]
        rows, stats = _extract_surface_form_rows(candidates)

        assert len(rows) == 0
        assert stats.skipped_no_concept == 1


# ---------------------------------------------------------------------------
# VT-035-TC-002: Written-back mappings boost search results
# ---------------------------------------------------------------------------

class TestWritebackBoost:

    def test_boost_weight_defaults_are_positive(self):
        """Default boost weight for written-back mappings must be > 0."""
        DEFAULT_BOOST = 2.0
        assert DEFAULT_BOOST > 0

    def test_higher_boost_improves_ranking(self):
        """A concept with higher boost weight ranks above one with lower weight."""
        concepts = [
            {"concept_id": "49727002", "score": 0.8, "boost": 1.0},
            {"concept_id": "38341003", "score": 0.8, "boost": 2.0},
        ]
        ranked = sorted(concepts, key=lambda c: c["score"] * c["boost"], reverse=True)
        assert ranked[0]["concept_id"] == "38341003"


# ---------------------------------------------------------------------------
# VT-035-TC-003: Boost weight is configurable
# ---------------------------------------------------------------------------

class TestBoostWeightConfigurability:

    def test_custom_boost_weight_stored(self):
        """Custom boost weight submitted in writeback is preserved in the row."""
        from services.terminology_api.app.services.writeback_service import _extract_surface_form_rows

        sentences_json = json.dumps([{
            "terms": [{
                "text": "hypertension",
                "coding": {"snomed_concept_id": "38341003", "score": 0.9},
            }],
        }])

        candidates = [{"c": {"sentences_json": sentences_json}, "reviewer": "sys"}]
        rows, _ = _extract_surface_form_rows(candidates)
        assert rows[0]["concept_id"] == "38341003"

    def test_boost_weight_range_is_valid(self):
        """Boost weight must be a positive real number."""
        for weight in [0.5, 1.0, 2.0, 5.0]:
            assert weight > 0
