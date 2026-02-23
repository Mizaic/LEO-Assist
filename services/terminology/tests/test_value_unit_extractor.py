"""Tests for the value/unit extractor component."""

import spacy

from services.terminology.nlp.extensions import set_extensions


def _make_nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("value_unit_extractor")
    return nlp


def test_extracts_blood_pressure():
    nlp = _make_nlp()
    doc = nlp("BP 120/80 mmHg noted")
    meas = [e for e in doc.ents if e.label_ == "MEASUREMENT"]
    assert len(meas) >= 1
    bp = meas[0]
    assert bp._.value == "120/80"
    assert bp._.unit == "mmHg"
    assert bp._.measurement_type == "blood_pressure"


def test_extracts_bmi():
    nlp = _make_nlp()
    doc = nlp("BMI 28.5 kg/m2")
    meas = [e for e in doc.ents if e._.measurement_type == "bmi"]
    assert len(meas) >= 1
    assert meas[0]._.value == "28.5"


def test_extracts_temperature():
    nlp = _make_nlp()
    doc = nlp("temp 37.2 degrees")
    meas = [e for e in doc.ents if e._.measurement_type == "temperature"]
    assert len(meas) >= 1
    assert meas[0]._.value == "37.2"


def test_extracts_hba1c():
    nlp = _make_nlp()
    doc = nlp("HbA1c 48 mmol/mol")
    meas = [e for e in doc.ents if e._.measurement_type == "hba1c"]
    assert len(meas) >= 1
    assert meas[0]._.value == "48"


def test_no_spurious_measurements():
    nlp = _make_nlp()
    doc = nlp("Patient is doing well")
    meas = [e for e in doc.ents if e.label_ == "MEASUREMENT"]
    assert len(meas) == 0
