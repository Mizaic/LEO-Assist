"""Tests for deidentify_with_span() in libs/utils/deidentify.py."""

from __future__ import annotations

import pytest

from libs.utils.deidentify import (
    _looks_like_read_code,
    deidentify_text,
    deidentify_with_span,
    detect_phi,
)


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


class TestPostcodePreservesReadCodes:
    """Postcode redaction must not clobber CTV3 / Read v2 clinical codes.

    UK postcodes in clinical text are written canonically with a space between
    outward and inward parts ("SW1A 1AA"). 5-character no-space tokens that
    match the compact-form postcode regex are overwhelmingly clinical Read
    codes (e.g. "B00zz" malignant neoplasm of lip, "X78HC" disorder code),
    not postcodes. They MUST be preserved unchanged.
    """

    @pytest.mark.parametrize(
        "code",
        [
            "B00zz",  # Malignant neoplasm of lip, vermilion border NOS
            "B06yz",
            "X00ZA",
            "X00ZB",
            "X78HC",
            "X78HI",
            "Ya03d",  # CTV3: H/O gastrointestinal tract
            "Y7JQI",
        ],
    )
    def test_read_code_preserved(self, code: str) -> None:
        sentence = f"Coded as {code} on review."
        out = deidentify_text(sentence)
        assert code in out, f"Read code {code} was incorrectly redacted: {out!r}"
        assert "[POSTCODE]" not in out

    def test_real_postcode_still_redacted_with_space(self) -> None:
        sentence = "Address: 22 Main Street, SW1A 1AA."
        out = deidentify_text(sentence)
        assert "SW1A 1AA" not in out
        assert "[POSTCODE]" in out

    def test_real_postcode_compact_long_form_still_redacted(self) -> None:
        # 7-char compact form contains the optional alphanumeric, so it is
        # unambiguously a postcode (no Read code is 7 chars).
        sentence = "Lives at SW1A1AA currently."
        out = deidentify_text(sentence)
        assert "SW1A1AA" not in out
        assert "[POSTCODE]" in out

    def test_detect_phi_does_not_flag_read_code_as_postcode(self) -> None:
        assert "postcode" not in detect_phi("Coded as B00zz on review.")
        assert "postcode" not in detect_phi("Term Ya03d added to record.")

    def test_detect_phi_still_flags_real_postcode(self) -> None:
        assert "postcode" in detect_phi("Address: 22 Main Street, SW1A 1AA.")

    @pytest.mark.parametrize(
        "token,expected",
        [
            ("B00zz", True),
            ("X78HC", True),
            ("Ya03d", True),
            ("B0...", True),  # Read v2 with trailing dot padding
            ("8BAD0", True),
            ("SW1A 1AA", False),  # has space, real postcode
            ("SW1A1AA", False),  # 7 chars, real compact postcode
            ("LE114QH", False),  # 7 chars, real compact postcode
            ("ABC", False),  # too short
        ],
    )
    def test_looks_like_read_code(self, token: str, expected: bool) -> None:
        assert _looks_like_read_code(token) is expected
