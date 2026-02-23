"""Tests for the Read code extractor component."""

import spacy

from services.terminology.nlp.extensions import set_extensions


def _make_nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("read_code_extractor")
    return nlp


def test_detects_read_v2_code():
    nlp = _make_nlp()
    doc = nlp("Coded as H33.. in the record")
    read_ents = [e for e in doc.ents if e.label_ == "READ_CODE"]
    assert len(read_ents) == 1
    assert read_ents[0]._.read_code == "H33"
    assert read_ents[0]._.source == "read_code"


def test_detects_multiple_codes():
    nlp = _make_nlp()
    doc = nlp("G30.. hypertension and C10.. diabetes")
    read_ents = [e for e in doc.ents if e.label_ == "READ_CODE"]
    assert len(read_ents) == 2


def test_ignores_non_read_patterns():
    nlp = _make_nlp()
    doc = nlp("The patient is 65 years old and weighs 80kg")
    read_ents = [e for e in doc.ents if e.label_ == "READ_CODE"]
    assert len(read_ents) == 0
