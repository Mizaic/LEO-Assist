"""Tests for the TF-IDF + ANN candidate generation."""

from services.terminology.nlp.kb.knowledge_base import Entity, KnowledgeBase


def test_knowledge_base_add_and_lookup():
    kb = KnowledgeBase()
    entity = Entity(
        concept_id="73211009",
        canonical_name="Diabetes mellitus",
        aliases=["diabetes", "DM", "sugar diabetes"],
        types=["T047"],
        definition="A metabolic disorder",
        cui="C0011849",
        icd10_codes=["E14.9"],
        read_codes=["C10.."],
    )
    kb.add_entity(entity)
    assert len(kb) == 1
    assert "diabetes mellitus" in kb.alias_to_cuis
    assert "73211009" in kb.alias_to_cuis["diabetes mellitus"]
    assert "73211009" in kb.alias_to_cuis["dm"]
    assert "73211009" in kb.alias_to_cuis["sugar diabetes"]


def test_knowledge_base_alias_to_multiple_cuis():
    kb = KnowledgeBase()
    e1 = Entity(
        concept_id="A1",
        canonical_name="Term X",
        aliases=["common alias"],
    )
    e2 = Entity(
        concept_id="A2",
        canonical_name="Term Y",
        aliases=["common alias"],
    )
    kb.add_entity(e1)
    kb.add_entity(e2)
    assert len(kb.alias_to_cuis["common alias"]) == 2


def test_knowledge_base_empty():
    kb = KnowledgeBase()
    assert len(kb) == 0
    assert "anything" not in kb.alias_to_cuis
