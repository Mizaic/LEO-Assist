"""Tests for the date extractor component."""

import spacy

from services.terminology.nlp.extensions import set_extensions


def _make_nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("date_extractor")
    return nlp


def test_extracts_uk_date():
    nlp = _make_nlp()
    doc = nlp("Seen on 15/03/2025 for follow up")
    dates = [e for e in doc.ents if e.label_ == "DATE"]
    assert len(dates) >= 1
    assert dates[0]._.temporal_type == "absolute"


def test_extracts_relative_date():
    nlp = _make_nlp()
    doc = nlp("Symptoms started 3 weeks ago")
    dates = [e for e in doc.ents if e.label_ == "DATE"]
    assert len(dates) >= 1
    assert dates[0]._.temporal_type == "relative"


def test_extracts_duration():
    nlp = _make_nlp()
    doc = nlp("For 2 weeks patient has had cough")
    dates = [e for e in doc.ents if e.label_ == "DATE"]
    assert len(dates) >= 1
    assert dates[0]._.temporal_type == "duration"


def test_extracts_month_name_date():
    nlp = _make_nlp()
    doc = nlp("Referred in January 2025")
    dates = [e for e in doc.ents if e.label_ == "DATE"]
    assert len(dates) >= 1
    assert dates[0]._.temporal_type == "absolute"
