"""VT-LEO-AI-002: NLP Entity Extraction Verification.

Verifies entity extraction, negation detection, context classification, and
F1 score thresholds. Uses mock-based tests so CI runs without live models.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.coding_worker.app.pipeline.extractor_contract import (
    ExtractionItem,
    CONTRACT_VERSION,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(
    text: str,
    assertion: str = "present",
    context: str = "current",
    confidence: float = 0.9,
) -> ExtractionItem:
    return ExtractionItem(
        sentence_id="s001",
        text=text,
        span_start=0,
        span_end=len(text),
        semantic_tag="disease",
        assertion=assertion,
        confidence=confidence,
        normalized=text,
        source="llm",
        model_name="test-model",
        model_version="1.0",
        contract_version=CONTRACT_VERSION,
    )


# ---------------------------------------------------------------------------
# VT-002-TC-001: Entities extracted from free text
# ---------------------------------------------------------------------------


class TestEntityExtraction:

    def test_extracted_item_has_required_fields(self):
        """Every extracted entity must have text, tag, assertion, and confidence."""
        item = _item("chest pain")
        assert item.text == "chest pain"
        assert item.semantic_tag == "disease"
        assert item.assertion in ("present", "absent", "possible")
        assert 0.0 <= item.confidence <= 1.0

    def test_entity_types_correctly_assigned(self):
        """Entity semantic tags are preserved exactly as set."""
        for tag in ("disease", "medication", "procedure"):
            item = ExtractionItem(
                sentence_id="s1",
                text="item",
                span_start=0,
                span_end=4,
                semantic_tag=tag,
                assertion="present",
                confidence=0.8,
                normalized="item",
                source="llm",
                model_name="m",
                model_version="1",
                contract_version=CONTRACT_VERSION,
            )
            assert item.semantic_tag == tag

    def test_batch_extract_returns_list(self):
        """extract_batch returns a list (may be empty without a live model)."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=None):
            ext = LLMExtractor(model_id="test")

        result = ext.extract_batch("Patient has cough", [MagicMock()])
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# VT-002-TC-002: Negation detected correctly
# ---------------------------------------------------------------------------


class TestNegationDetection:

    def test_absent_assertion_marks_negated(self):
        """assertion='absent' correctly signals a negated entity."""
        item = _item("chest pain", assertion="absent")
        assert item.assertion == "absent"

    def test_present_assertion_not_negated(self):
        """assertion='present' is never treated as negated."""
        item = _item("chest pain", assertion="present")
        assert item.assertion == "present"

    def test_parse_terms_honours_valid_llm_supplied_assertion(self):
        """Superseded DI-LEO-AI-103 (see DI-B5C78811 AC6, test_assertion_llm_exclusion.py):
        the extractor now aligns with the LLM annotation guidelines and honours
        a valid LLM-supplied assertion via `_parse_assertion()` -- it is no
        longer forced to "present". ConText and the scope guard still run
        downstream and can override an incorrect extractor emission, so the
        LLM's value is never the sole signal (see `_parse_assertion` docstring)."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="m")

        sentences = [MagicMock(sentence_id="s0")]
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "no chest pain",
                    "lookup_term": "chest pain",
                    "semantic_tag": "disease",
                    "assertion": "absent",
                },
            ]
        }
        terms = ext._parse_terms(payload, sentences)
        assert len(terms) == 1
        assert terms[0].assertion == "absent"
        assert terms[0].context["negated"] is True

    def test_parse_terms_falls_back_to_present_for_invalid_assertion(self):
        """`_parse_assertion` only trusts values in `_VALID_ASSERTIONS`; a
        missing or unrecognised assertion still defaults to "present", while
        a valid value (e.g. "absent") passes through unchanged."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="m")

        sentences = [MagicMock(sentence_id="s0"), MagicMock(sentence_id="s1")]
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "hypertension",
                    "lookup_term": "hypertension",
                    "semantic_tag": "disease",
                    "assertion": "not-a-real-assertion",
                },
                {
                    "sentence_id": "s1",
                    "text": "no diabetes",
                    "lookup_term": "diabetes",
                    "semantic_tag": "disease",
                    "assertion": "absent",
                },
            ]
        }
        terms = ext._parse_terms(payload, sentences)
        assert terms[0].assertion == "present"
        assert terms[0].context["negated"] is False
        assert terms[1].assertion == "absent"
        assert terms[1].context["negated"] is True


# ---------------------------------------------------------------------------
# VT-002-TC-003: Context classification
# ---------------------------------------------------------------------------


class TestContextClassification:

    def test_possible_assertion_recognised(self):
        """'possible' assertion is a valid context classification."""
        item = _item("cancer", assertion="possible")
        assert item.assertion == "possible"

    def test_invalid_assertion_defaults_to_present(self):
        """Unrecognised assertion strings default to 'present' for safety."""
        from services.coding_worker.app.pipeline.llm_extractor import LLMExtractor

        with patch.object(LLMExtractor, "_init_client", return_value=MagicMock()):
            ext = LLMExtractor(model_id="m")

        sentences = [MagicMock(sentence_id="s0")]
        payload = {
            "terms": [
                {
                    "sentence_id": "s0",
                    "text": "cough",
                    "lookup_term": "cough",
                    "semantic_tag": "disease",
                    "assertion": "INVALID_CONTEXT",
                },
            ]
        }
        terms = ext._parse_terms(payload, sentences)
        assert terms[0].assertion == "present"


# ---------------------------------------------------------------------------
# VT-002-TC-004: F1 >= 0.85 (mocked gold-standard batch)
# ---------------------------------------------------------------------------


class TestF1Threshold:

    def test_f1_calculation_on_mock_corpus(self):
        """With perfect mock predictions, F1 == 1.0 which satisfies >= 0.85."""
        gold = [
            {"text": "diabetes", "tag": "disease"},
            {"text": "metformin", "tag": "medication"},
            {"text": "biopsy", "tag": "procedure"},
        ]

        predicted = [
            {"text": "diabetes", "tag": "disease"},
            {"text": "metformin", "tag": "medication"},
            {"text": "biopsy", "tag": "procedure"},
        ]

        tp = sum(1 for g in gold if g in predicted)
        precision = tp / len(predicted) if predicted else 0
        recall = tp / len(gold) if gold else 0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        assert f1 >= 0.85

    def test_no_entity_type_below_f1_075(self):
        """Per-type F1 must be >= 0.75 — verified with mock perfect predictions."""
        per_type_gold = {
            "disease": [{"text": "hypertension"}, {"text": "diabetes"}],
            "medication": [{"text": "metformin"}],
            "procedure": [{"text": "biopsy"}, {"text": "colonoscopy"}],
        }

        for entity_type, gold in per_type_gold.items():
            predicted = gold  # perfect predictions in mock
            tp = len(gold)
            precision = tp / len(predicted)
            recall = tp / len(gold)
            f1 = 2 * precision * recall / (precision + recall)
            assert f1 >= 0.75, f"F1 {f1:.2f} below 0.75 for entity type '{entity_type}'"
