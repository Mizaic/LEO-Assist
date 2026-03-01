"""Tests for terminology writeback service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.terminology_writeback_service import (
    _extract_surface_form_rows,
    _normalize,
    writeback_approved_terms,
)


class TestNormalize:
    def test_basic(self) -> None:
        assert _normalize("Diabetes mellitus") == "diabetes mellitus"

    def test_strips_punctuation(self) -> None:
        assert _normalize("H/O: asthma") == "h o asthma"

    def test_collapses_spaces(self) -> None:
        assert _normalize("  blood   pressure  ") == "blood pressure"


class TestExtractSurfaceFormRows:
    def _make_record(self, terms: list[dict], reviewer: str = "dr.smith") -> dict:
        sentences = [{"sentence_id": "s0", "terms": terms}]
        return {
            "c": {
                "candidate_id": "c1",
                "patient_id": "p1",
                "encounter_id": "enc1",
                "sentences_json": json.dumps(sentences),
            },
            "reviewer": reviewer,
        }

    def test_extracts_term_with_concept(self) -> None:
        record = self._make_record([{
            "text": "Diabetes",
            "coding": {"snomed_concept_id": "73211009", "score": 0.95},
        }])
        rows, stats = _extract_surface_form_rows([record])
        assert len(rows) == 1
        assert rows[0]["form"] == "Diabetes"
        assert rows[0]["normalized"] == "diabetes"
        assert rows[0]["concept_id"] == "73211009"
        assert rows[0]["confidence"] == 0.95
        assert rows[0]["approved_by"] == "dr.smith"
        assert stats.eligible == 1

    def test_skips_no_concept(self) -> None:
        record = self._make_record([{
            "text": "unknown",
            "coding": {"snomed_concept_id": None},
        }])
        rows, stats = _extract_surface_form_rows([record])
        assert len(rows) == 0
        assert stats.skipped_no_concept == 1

    def test_deduplicates(self) -> None:
        record = self._make_record([
            {"text": "Diabetes", "coding": {"snomed_concept_id": "73211009"}},
            {"text": "diabetes", "coding": {"snomed_concept_id": "73211009"}},
        ])
        rows, stats = _extract_surface_form_rows([record])
        assert len(rows) == 1
        assert stats.eligible == 1


class TestWritebackApprovedTerms:
    def test_no_approved(self) -> None:
        patient_session = MagicMock()
        patient_session.run.return_value = []
        coding_session = MagicMock()

        result = writeback_approved_terms(
            patient_session=patient_session,
            coding_session=coding_session,
        )

        assert result["surface_forms_written"] == 0
        coding_session.run.assert_not_called()

    def test_writes_surface_forms(self) -> None:
        sentences = [{"sentence_id": "s0", "terms": [{
            "text": "BP",
            "coding": {"snomed_concept_id": "75367002", "score": 0.9},
        }]}]
        patient_session = MagicMock()
        patient_session.run.return_value = [{
            "c": {
                "candidate_id": "c1",
                "patient_id": "p1",
                "encounter_id": "enc1",
                "sentences_json": json.dumps(sentences),
            },
            "reviewer": "dr.jones",
        }]

        written_record = MagicMock()
        written_record.__getitem__ = lambda self, key: 1
        coding_session = MagicMock()
        coding_result = MagicMock()
        coding_result.single.return_value = written_record
        coding_session.run.return_value = coding_result

        result = writeback_approved_terms(
            patient_session=patient_session,
            coding_session=coding_session,
        )

        assert result["surface_forms_written"] == 1
        assert result["candidates_scanned"] == 1
        coding_session.run.assert_called_once()
