"""Tests for the confidence scorer component."""

import spacy

from services.terminology.nlp.extensions import set_extensions


def _make_nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("confidence_scorer")
    return nlp


def test_confidence_defaults_to_zero_without_linking():
    nlp = _make_nlp()
    doc = nlp("Some text")
    for ent in doc.ents:
        assert 0.0 <= ent._.confidence <= 1.0
