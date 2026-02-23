"""Tests for the abbreviation detector component."""

import spacy
from spacy.tokens import Span

from services.terminology.nlp.extensions import set_extensions


def _make_nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe(
        "abbreviation_detector",
        config={"language_code": "en_gb"},
    )
    return nlp


def test_gp_dictionary_detects_known_abbreviation():
    nlp = _make_nlp()
    doc = nlp("SOB at rest")
    found = [t for t in doc if t._.expanded_form is not None]
    assert len(found) >= 1
    assert found[0]._.expanded_form == "shortness of breath"


def test_gp_dictionary_detects_nad():
    nlp = _make_nlp()
    doc = nlp("O/E NAD")
    nad_tokens = [t for t in doc if t.text.lower() == "nad"]
    assert len(nad_tokens) >= 1
    assert nad_tokens[0]._.expanded_form == "nothing abnormal detected"


def test_schwartz_hearst_detects_parenthetical():
    nlp = _make_nlp()
    doc = nlp("shortness of breath (SOB) noted at rest. SOB worsening.")
    abbreviations = doc._.abbreviations
    assert len(abbreviations) >= 1
    abbrev_texts = [a.text for a in abbreviations]
    assert "SOB" in abbrev_texts


def test_doc_abbreviations_populated():
    nlp = _make_nlp()
    doc = nlp("Patient has HTN and DM")
    assert isinstance(doc._.abbreviations, list)
