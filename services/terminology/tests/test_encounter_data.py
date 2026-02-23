"""Integration tests against encounter_analysis.json sample data.

Tests that the pipeline produces sensible output for realistic GP encounter
text. These tests run the minimal pipeline (no KB/Neo4j required).
"""

import pytest
import spacy

from services.terminology.nlp.extensions import set_extensions


SAMPLE_ENCOUNTERS = [
    "PMH: DM type 2, HTN. C/O rectal bleeding for 2 weeks. FIT positive. "
    "2ww referral to colorectal.",
    "O/E NAD. BP 120/80 mmHg. BMI 28.5. No lymphadenopathy. "
    "Abdo soft, non-tender.",
    "Hx: SOB (shortness of breath) on exertion for 3 weeks. "
    "No chest pain. No haemoptysis. Ex-smoker.",
    "Imp: ?lung cancer. Plan: urgent CXR. 2ww referral to respiratory. "
    "Safety net: return if SOB worsens.",
    "Results: PSA 4.2. eGFR 65. HbA1c 52 mmol/mol. LFTs normal.",
]


@pytest.fixture(scope="module")
def nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("abbreviation_detector", config={"language_code": "en_gb"})
    nlp.add_pipe("read_code_extractor")
    nlp.add_pipe("value_unit_extractor")
    nlp.add_pipe("date_extractor")
    nlp.add_pipe("confidence_scorer")
    return nlp


def test_encounter_processing_succeeds(nlp):
    """All sample encounters process without errors."""
    for text in SAMPLE_ENCOUNTERS:
        doc = nlp(text)
        assert doc is not None
        assert len(doc) > 0


def test_abbreviations_detected_in_encounters(nlp):
    doc = nlp(SAMPLE_ENCOUNTERS[0])
    abbrevs = {a.text.lower() for a in doc._.abbreviations}
    assert len(abbrevs) > 0


def test_sob_expanded_via_schwartz_hearst(nlp):
    doc = nlp(SAMPLE_ENCOUNTERS[2])
    sob_spans = [a for a in doc._.abbreviations if a.text == "SOB"]
    has_expansion = any(
        s._.long_form is not None or (
            len(s) == 1 and s[0]._.expanded_form is not None
        )
        for s in sob_spans
    )
    assert has_expansion


def test_blood_pressure_in_examination(nlp):
    doc = nlp(SAMPLE_ENCOUNTERS[1])
    bp = [e for e in doc.ents if e._.measurement_type == "blood_pressure"]
    assert len(bp) >= 1
    assert bp[0]._.value == "120/80"


def test_bmi_extracted(nlp):
    doc = nlp(SAMPLE_ENCOUNTERS[1])
    bmi = [e for e in doc.ents if e._.measurement_type == "bmi"]
    assert len(bmi) >= 1
    assert bmi[0]._.value == "28.5"


def test_hba1c_extracted(nlp):
    doc = nlp(SAMPLE_ENCOUNTERS[4])
    hba1c = [e for e in doc.ents if e._.measurement_type == "hba1c"]
    assert len(hba1c) >= 1
    assert hba1c[0]._.value == "52"


def test_duration_extracted(nlp):
    doc = nlp(SAMPLE_ENCOUNTERS[0])
    dates = [e for e in doc.ents if e.label_ == "DATE"]
    durations = [d for d in dates if d._.temporal_type == "duration"]
    assert len(durations) >= 1
