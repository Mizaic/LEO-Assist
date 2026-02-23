"""Tests for the entity linker component."""

import spacy

from services.terminology.nlp.extensions import set_extensions


def _make_nlp():
    set_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("clinical_entity_linker")
    return nlp


def test_entity_linker_initialises_without_kb():
    """Linker should initialise even without KB/index (no linking, just passthrough)."""
    nlp = _make_nlp()
    doc = nlp("Patient has diabetes")
    assert doc is not None


def test_entity_linker_preserves_existing_ents():
    set_extensions()
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns([{"label": "CONDITION", "pattern": "diabetes"}])
    nlp.add_pipe("clinical_entity_linker")
    doc = nlp("Patient has diabetes")
    assert len(doc.ents) == 1
    assert doc.ents[0].text == "diabetes"


def test_entity_linker_sets_source():
    set_extensions()
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns([{"label": "CONDITION", "pattern": "diabetes"}])
    nlp.add_pipe("clinical_entity_linker")
    doc = nlp("Patient has diabetes")
    for ent in doc.ents:
        assert ent._.source is not None
