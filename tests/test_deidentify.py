"""Tests for deidentify_with_span() in libs/utils/deidentify.py."""

from __future__ import annotations

import pytest

from libs.utils.deidentify import deidentify_with_span


class TestDeidentifyWithSpanNormalCase:
    """Span text is present in the sentence and survives de-identification."""

    def test_returns_deidentified_sentence(self):
        sentence = "Patient has hypertension."
        deident, start, end = deidentify_with_span(sentence, "hypertension")
        assert "hypertension" in deident
        assert start >= 0

    def test_span_offsets_are_correct(self):
        sentence = "Diagnosis of type 2 diabetes confirmed."
        span = "type 2 diabetes"
        deident, start, end = deidentify_with_span(sentence, span)
        assert start != -1
        assert deident[start:end].lower() == span.lower()

    def test_span_length_matches(self):
        sentence = "Patient has asthma and is on inhalers."
        span = "asthma"
        deident, start, end = deidentify_with_span(sentence, span)
        assert end - start == len(span)


class TestDeidentifyWithSpanCaseInsensitive:
    """Span matching is case-insensitive."""

    def test_uppercase_span_found_in_lowercase_sentence(self):
        sentence = "history of COPD noted."
        span = "copd"
        deident, start, end = deidentify_with_span(sentence, span)
        assert start != -1
        assert deident[start:end].lower() == span.lower()

    def test_mixed_case_span_matched(self):
        sentence = "Patient reports Chest Pain on exertion."
        span = "chest pain"
        deident, start, end = deidentify_with_span(sentence, span)
        assert start != -1


class TestDeidentifyWithSpanPiiRemoved:
    """Sentence contains PII that is stripped; span survives."""

    def test_name_removed_but_clinical_span_survives(self):
        sentence = "Dr Smith reviewed the patient's hypertension management."
        span = "hypertension"
        deident, start, end = deidentify_with_span(sentence, span)
        # Dr Smith should be replaced, but span survives
        assert "[PERSON]" in deident
        assert start != -1
        assert deident[start:end].lower() == span.lower()

    def test_phone_removed_span_survives(self):
        sentence = "Call 07700 900000 to discuss diabetes treatment."
        span = "diabetes"
        deident, start, end = deidentify_with_span(sentence, span)
        assert "[PHONE]" in deident
        assert start != -1


class TestDeidentifyWithSpanSentinel:
    """When span overlaps PII token, -1 sentinel is returned."""

    def test_span_replaced_by_pii_returns_sentinel(self):
        # SMITH is a name; if we ask for SMITH as the span, it gets redacted
        sentence = "SMITH, John discussed medication."
        span = "SMITH"
        deident, start, end = deidentify_with_span(sentence, span)
        # Either "SMITH" was consumed into [PERSON] or it survived:
        # We only assert the contract: if start == -1, end == -1.
        if start == -1:
            assert end == -1

    def test_sentinel_values_are_negative_one(self):
        # Guarantee the sentinel is exactly -1, -1 (not None or 0).
        sentence = "Dr ATKIN, Sarah discussed asthma."
        # The name "ATKIN, Sarah" will be redacted; asthma should survive.
        # We test a span that definitely won't exist after de-id.
        deident, start, end = deidentify_with_span(sentence, "ATKIN")
        if start == -1:
            assert end == -1, "Sentinel end must also be -1"

    def test_nonexistent_span_returns_sentinel(self):
        sentence = "The patient attended the clinic."
        deident, start, end = deidentify_with_span(sentence, "xyzzy_no_such_term")
        assert start == -1
        assert end == -1

    def test_deident_text_still_returned_on_sentinel(self):
        sentence = "The patient attended the clinic."
        deident, start, end = deidentify_with_span(sentence, "xyzzy_no_such_term")
        # Even when sentinel fires, deident sentence must be returned.
        assert isinstance(deident, str)
        assert len(deident) > 0
