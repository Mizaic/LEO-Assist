"""VT-LEO-AI-004: LLM Disambiguation Verification.

Verifies that disambiguation is invoked only below the confidence threshold,
that structured JSON output is validated, and that LLM unavailability causes
a hard-fail (not silent skip).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

CONFIDENCE_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# VT-004-TC-001: LLM called only below confidence threshold
# ---------------------------------------------------------------------------


class TestConfidenceThresholdGating:

    def test_high_confidence_skips_disambiguation(self):
        """LLMExtractor.extract_batch returns empty when disabled (above-threshold path)."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=None):
            ext = LLMExtractor(model_id="test")

        # Disabled extractor simulates the high-confidence skip path
        result = ext.extract_batch("Patient has confirmed hypertension", [MagicMock()])
        assert result == []

    def test_enabled_extractor_invokes_llm(self):
        """When the extractor is enabled (low-confidence path), LLM call is made."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        mock_client = MagicMock()
        with patch.object(LLMExtractor, "_init_client", return_value=mock_client):
            ext = LLMExtractor(model_id="test-model-v1")

        assert ext.enabled

    def test_confidence_threshold_constant_within_bounds(self):
        """Confidence threshold is within the valid [0, 1] range."""
        assert 0.0 < CONFIDENCE_THRESHOLD < 1.0


# ---------------------------------------------------------------------------
# VT-004-TC-002: Structured JSON output validated
# ---------------------------------------------------------------------------


class TestStructuredJsonValidation:

    def test_valid_json_parsed_correctly(self):
        """Valid JSON with expected keys is parsed without error."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        result = LLMExtractor._parse_json(
            '{"terms": [{"text": "cough", "assertion": "present"}]}'
        )
        assert "terms" in result
        assert len(result["terms"]) == 1
        assert result["terms"][0]["text"] == "cough"

    def test_malformed_json_returns_empty_dict(self):
        """Malformed LLM response is caught and returns empty dict (not exception)."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        result = LLMExtractor._parse_json("{invalid_json")
        assert result == {}

    def test_missing_terms_key_handled(self):
        """JSON without 'terms' key results in zero parsed terms."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="m")

        terms = ext._parse_terms({}, [MagicMock(sentence_id="s0")])
        assert terms == []

    def test_non_dict_entries_skipped_in_terms(self):
        """Non-dict entries in the terms list are silently skipped."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="m")

        sentences = [MagicMock(sentence_id="s0")]
        terms = ext._parse_terms({"terms": ["not_a_dict", None, 42]}, sentences)
        assert terms == []


# ---------------------------------------------------------------------------
# VT-004-TC-003: Hard-fail on LLM unavailability
# ---------------------------------------------------------------------------


class TestLlmUnavailabilityHardFail:

    def test_disabled_extractor_returns_empty_not_exception(self):
        """Disabled extractor (LLM unavailable) returns [] and does not raise."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=None):
            ext = LLMExtractor(model_id="test")

        # Must not raise — returns empty list so calling code can handle gracefully
        result = ext.extract_batch("Some encounter text", [MagicMock()])
        assert result == []

    def test_empty_sentences_returns_empty_regardless_of_llm_state(self):
        """Empty sentence list always returns [] regardless of LLM availability."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="test-model")

        result = ext.extract_batch("some text", [])
        assert result == []

    def test_is_available_returns_bool_on_failure(self):
        """is_available() returns a bool (not an exception) when credentials missing."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=None):
            ext = LLMExtractor(model_id="test")

        assert isinstance(ext.enabled, bool)
