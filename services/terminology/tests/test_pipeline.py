"""Integration tests for the full NLP pipeline.

These tests verify the pipeline assembles correctly and produces expected
output structure. They do NOT require a Neo4j connection or pre-built index.
"""

import pytest
import spacy

from services.terminology.nlp.extensions import set_extensions


@pytest.fixture(scope="module")
def nlp_minimal():
    """Minimal pipeline without entity linker KB or Neo4j."""
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("abbreviation_detector", config={"language_code": "en_gb"})
    nlp.add_pipe("read_code_extractor")
    nlp.add_pipe("value_unit_extractor")
    nlp.add_pipe("date_extractor")
    nlp.add_pipe("confidence_scorer")
    return nlp


def test_pipeline_processes_text(nlp_minimal):
    doc = nlp_minimal("PMH: DM, HTN. C/O SOB for 2 weeks. O/E NAD. BP 120/80.")
    assert doc is not None
    assert len(doc) > 0


def test_pipeline_abbreviations_detected(nlp_minimal):
    doc = nlp_minimal("SOB at rest, NAD on examination")
    abbrevs = doc._.abbreviations
    abbrev_tokens = {a.text.lower() for a in abbrevs}
    assert "sob" in abbrev_tokens or "nad" in abbrev_tokens


def test_pipeline_bp_extracted(nlp_minimal):
    doc = nlp_minimal("BP 130/85 mmHg")
    bp_ents = [e for e in doc.ents if e._.measurement_type == "blood_pressure"]
    assert len(bp_ents) >= 1
    assert bp_ents[0]._.value == "130/85"


def test_pipeline_date_extracted(nlp_minimal):
    doc = nlp_minimal("Seen on 15/01/2025, symptoms for 3 weeks")
    date_ents = [e for e in doc.ents if e.label_ == "DATE"]
    assert len(date_ents) >= 1


def test_pipeline_read_code_extracted(nlp_minimal):
    doc = nlp_minimal("H33.. asthma noted")
    read_ents = [e for e in doc.ents if e.label_ == "READ_CODE"]
    assert len(read_ents) == 1
    assert read_ents[0]._.read_code == "H33"


def test_pipeline_confidence_set(nlp_minimal):
    doc = nlp_minimal("H33.. asthma")
    for ent in doc.ents:
        assert hasattr(ent._, "confidence")
        assert 0.0 <= ent._.confidence <= 1.0
