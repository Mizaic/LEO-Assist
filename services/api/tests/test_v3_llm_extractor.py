"""Tests for V3 LLM extractor."""

from __future__ import annotations

import pytest

from app.services.v3.llm_extractor import ExtractedTerm, LLMExtractor
from app.services.v3.sentence_splitter import SentenceChunk


class TestLLMExtractorFallback:
    """Test extraction when LLM is disabled (fallback mode)."""

    def test_extract_empty_sentences(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        result = extractor.extract_batch("Some text", [])
        assert result == []

    def test_extract_fallback_produces_terms(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        chunks = [
            SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25),
        ]
        result = extractor.extract_batch("Patient has hypertension.", chunks)
        assert len(result) >= 1
        assert all(isinstance(t, ExtractedTerm) for t in result)
        assert all(t.sentence_id == "s0" for t in result)
        assert all(t.semantic_tag == "Other" for t in result)
        assert all("context" in dir(t) for t in result)
        assert all("modifiers" in dir(t) for t in result)

    def test_extract_fallback_context_fields(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        chunks = [
            SentenceChunk(sentence_id="s0", text="No diabetes.", start=0, end=12),
        ]
        result = extractor.extract_batch("No diabetes.", chunks)
        assert len(result) >= 1
        term = result[0]
        assert hasattr(term, "context")
        assert "negated" in term.context
        assert "uncertain" in term.context
        assert "historical" in term.context
        assert "subject" in term.context
        assert "temporality" in term.context


class TestLLMExtractorParsing:
    """Test JSON parsing of LLM responses."""

    def test_parse_terms_valid_payload(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "hypertension",
                    "semantic_tag": "Disease",
                    "context": {"negated": False, "uncertain": False, "historical": False, "subject": "patient", "temporality": "present"},
                    "modifiers": {},
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 1
        assert result[0].text == "hypertension"
        assert result[0].semantic_tag == "Disease"
        assert result[0].sentence_id == "s0"

    def test_parse_terms_ignores_invalid_sentence_id(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {"sentence_id": "s99", "text": "hypertension", "semantic_tag": "Disease", "context": {}, "modifiers": {}},
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 0

    def test_parse_terms_ignores_empty_text(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {"sentence_id": "s0", "text": "", "semantic_tag": "Disease", "context": {}, "modifiers": {}},
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 0
