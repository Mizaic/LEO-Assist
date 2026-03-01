"""Tests for services/coding-worker/app/pipeline/llm_extractor.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestExtractedTerm:

    def test_frozen_dataclass(self):
        from services.coding_worker.app.pipeline.llm_extractor import ExtractedTerm

        term = ExtractedTerm(
            sentence_id="s0",
            text="cough",
            lookup_term="cough",
            semantic_tag="finding",
            assertion="present",
            context={"negated": False},
            modifiers={},
        )
        assert term.sentence_id == "s0"
        assert term.assertion == "present"
        with pytest.raises(AttributeError):
            term.text = "other"


class TestLLMExtractor:

    def test_disabled_when_no_client(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=None):
            ext = LLMExtractor(model_id="test-model")
        assert not ext.enabled

    def test_disabled_when_unconfigured(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="unconfigured")
        assert not ext.enabled

    def test_enabled_with_client_and_model(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="test-model-v1")
        assert ext.enabled

    def test_extract_batch_returns_empty_when_disabled(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=None):
            ext = LLMExtractor(model_id="test")
        result = ext.extract_batch("some text", [MagicMock()])
        assert result == []

    def test_extract_batch_returns_empty_for_empty_sentences(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="test-model")
        result = ext.extract_batch("some text", [])
        assert result == []


class TestParseJson:

    def test_valid_json(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        result = LLMExtractor._parse_json('{"terms": []}')
        assert result == {"terms": []}

    def test_json_with_surrounding_text(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        result = LLMExtractor._parse_json('Here is the result: {"terms": [{"text": "cough"}]}')
        assert "terms" in result

    def test_empty_string(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        result = LLMExtractor._parse_json("")
        assert result == {}

    def test_invalid_json(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        result = LLMExtractor._parse_json("not json at all")
        assert result == {}


class TestParseTerms:

    def _make_extractor(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            return LLMExtractor(model_id="m")

    def test_valid_terms(self):
        ext = self._make_extractor()
        sentences = [MagicMock(sentence_id="s0"), MagicMock(sentence_id="s1")]

        payload = {"terms": [
            {"sentence_id": "s0", "text": "cough", "lookup_term": "cough", "semantic_tag": "finding", "assertion": "present"},
            {"sentence_id": "s1", "text": "headache", "lookup_term": "headache", "semantic_tag": "finding", "assertion": "absent"},
        ]}
        result = ext._parse_terms(payload, sentences)
        assert len(result) == 2
        assert result[0].assertion == "present"
        assert result[0].context["negated"] is False
        assert result[1].assertion == "absent"
        assert result[1].context["negated"] is True

    def test_filters_invalid_sentence_ids(self):
        ext = self._make_extractor()
        sentences = [MagicMock(sentence_id="s0")]

        payload = {"terms": [
            {"sentence_id": "s0", "text": "valid"},
            {"sentence_id": "s99", "text": "invalid_sid"},
        ]}
        result = ext._parse_terms(payload, sentences)
        assert len(result) == 1

    def test_defaults_to_present_for_invalid_assertion(self):
        ext = self._make_extractor()
        sentences = [MagicMock(sentence_id="s0")]

        payload = {"terms": [
            {"sentence_id": "s0", "text": "cough", "assertion": "INVALID"},
        ]}
        result = ext._parse_terms(payload, sentences)
        assert result[0].assertion == "present"

    def test_empty_terms(self):
        ext = self._make_extractor()
        result = ext._parse_terms({"terms": []}, [])
        assert result == []

    def test_skips_non_dict_entries(self):
        ext = self._make_extractor()
        sentences = [MagicMock(sentence_id="s0")]

        payload = {"terms": ["not_a_dict", None, 42]}
        result = ext._parse_terms(payload, sentences)
        assert result == []


class TestBuildUserPrompt:

    def test_prompt_format(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        sentences = [MagicMock(sentence_id="s0", text="Patient has cough")]
        prompt = LLMExtractor._build_user_prompt("Full encounter text", sentences)
        assert "Full encounter text" in prompt
        assert "s0" in prompt


class TestExtractText:

    def test_extract_from_response(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        response = {
            "output": {"message": {"content": [{"text": '{"terms": []}'}]}}
        }
        result = LLMExtractor._extract_text(response)
        assert result == '{"terms": []}'

    def test_empty_content(self):
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        response = {"output": {"message": {"content": []}}}
        result = LLMExtractor._extract_text(response)
        assert result == ""
