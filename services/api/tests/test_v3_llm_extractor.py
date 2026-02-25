"""Tests for V3 LLM extractor."""

from __future__ import annotations

import pytest

from app.services.v3.llm_extractor import (
    ExtractionError,
    ExtractedTerm,
    LLMExtractor,
    _ASSERTION_TO_CONTEXT,
    _VALID_ASSERTIONS,
    assertion_to_context,
)
from app.services.v3.sentence_splitter import SentenceChunk


class TestLLMExtractorHardFail:
    """Extraction must raise ExtractionError when LLM is unavailable."""

    def test_extract_empty_sentences_returns_empty(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        terms, usage = extractor.extract_batch("Some text", [])
        assert terms == []
        assert usage.llm_calls == 0
        assert usage.total_tokens == 0

    def test_disabled_extractor_raises(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        chunks = [
            SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25),
        ]
        with pytest.raises(ExtractionError, match="not enabled"):
            extractor.extract_batch("Patient has hypertension.", chunks)


class TestLLMExtractorParsing:
    """Test JSON parsing of LLM responses with new 5-field schema."""

    def test_parse_terms_valid_payload(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "hypertension",
                    "lookup_term": "hypertension",
                    "semantic_tag": "disorder",
                    "assertion": "present",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 1
        assert result[0].text == "hypertension"
        assert result[0].lookup_term == "hypertension"
        assert result[0].semantic_tag == "disorder"
        assert result[0].assertion == "present"
        assert result[0].context["negated"] is False

    def test_parse_terms_abbreviation_expansion(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "HTN",
                    "lookup_term": "hypertension",
                    "semantic_tag": "disorder",
                    "assertion": "present",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Known HTN.", start=0, end=10)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 1
        assert result[0].text == "HTN"
        assert result[0].lookup_term == "hypertension"

    def test_parse_terms_absent_assertion(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "chest pain",
                    "lookup_term": "chest pain",
                    "semantic_tag": "finding",
                    "assertion": "absent",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="No chest pain.", start=0, end=14)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 1
        assert result[0].assertion == "absent"
        assert result[0].context["negated"] is True

    def test_parse_terms_ignores_invalid_sentence_id(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s99",
                    "text": "hypertension",
                    "lookup_term": "hypertension",
                    "semantic_tag": "disorder",
                    "assertion": "present",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 0

    def test_parse_terms_ignores_empty_text(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "",
                    "lookup_term": "",
                    "semantic_tag": "disorder",
                    "assertion": "present",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Patient has hypertension.", start=0, end=25)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 0

    def test_parse_terms_defaults_missing_lookup_term(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "COPD",
                    "semantic_tag": "disorder",
                    "assertion": "present",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Known COPD.", start=0, end=11)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 1
        assert result[0].lookup_term == "COPD"

    def test_parse_terms_invalid_assertion_defaults_present(self) -> None:
        extractor = LLMExtractor(model_id="unconfigured", region=None)
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "asthma",
                    "lookup_term": "asthma",
                    "semantic_tag": "disorder",
                    "assertion": "INVALID_VALUE",
                },
            ]
        }
        chunks = [SentenceChunk(sentence_id="s0", text="Has asthma.", start=0, end=11)]
        result = extractor._parse_terms(payload, chunks)
        assert len(result) == 1
        assert result[0].assertion == "present"


class TestAssertionMapping:
    """Verify assertion_to_context produces correct context dicts for all 6 values."""

    def test_present(self) -> None:
        ctx = assertion_to_context("present")
        assert ctx["negated"] is False
        assert ctx["uncertain"] is False
        assert ctx["historical"] is False
        assert ctx["subject"] == "patient"
        assert ctx["temporality"] == "present"

    def test_absent(self) -> None:
        ctx = assertion_to_context("absent")
        assert ctx["negated"] is True
        assert ctx["uncertain"] is False
        assert ctx["subject"] == "patient"

    def test_possible(self) -> None:
        ctx = assertion_to_context("possible")
        assert ctx["uncertain"] is True
        assert ctx["negated"] is False

    def test_historical(self) -> None:
        ctx = assertion_to_context("historical")
        assert ctx["historical"] is True
        assert ctx["temporality"] == "past"
        assert ctx["negated"] is False

    def test_hypothetical(self) -> None:
        ctx = assertion_to_context("hypothetical")
        assert ctx["historical"] is False
        assert ctx["temporality"] == "hypothetical"
        assert ctx["subject"] == "patient"

    def test_family(self) -> None:
        ctx = assertion_to_context("family")
        assert ctx["subject"] == "family"
        assert ctx["negated"] is False
        assert ctx["temporality"] == "unknown"

    def test_unknown_assertion_defaults_to_present(self) -> None:
        ctx = assertion_to_context("bogus_value")
        assert ctx == assertion_to_context("present")

    def test_all_valid_assertions_have_mappings(self) -> None:
        for a in _VALID_ASSERTIONS:
            ctx = assertion_to_context(a)
            assert "negated" in ctx
            assert "subject" in ctx
            assert "temporality" in ctx

    def test_returns_new_dict_each_call(self) -> None:
        a = assertion_to_context("present")
        b = assertion_to_context("present")
        assert a == b
        assert a is not b
