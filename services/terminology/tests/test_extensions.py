"""Tests for spaCy extension registration."""

import spacy
from spacy.tokens import Doc, Span, Token

from services.terminology.nlp.extensions import set_extensions


def test_set_extensions_registers_all_span_attrs():
    set_extensions()
    expected = [
        "kb_ents", "long_form", "cui", "snomed_code", "snomed_term",
        "icd10_codes", "read_code", "linker_score", "confidence", "source",
        "is_resolved", "is_abbreviation", "value", "unit", "measurement_type",
        "date_value", "temporal_type",
    ]
    for attr in expected:
        assert Span.has_extension(attr), f"Missing Span extension: {attr}"


def test_set_extensions_registers_token_attrs():
    set_extensions()
    assert Token.has_extension("expanded_form")


def test_set_extensions_registers_doc_attrs():
    set_extensions()
    assert Doc.has_extension("abbreviations")


def test_set_extensions_idempotent():
    set_extensions()
    set_extensions()
    assert Span.has_extension("kb_ents")
