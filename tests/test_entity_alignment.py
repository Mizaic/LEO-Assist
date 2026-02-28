"""Tests for multi-model entity alignment and consensus scoring."""
from __future__ import annotations

import pytest
from services.api.app.services.entity_alignment import (
    AlignedEntity,
    ConsensusResult,
    _compute_entity_confidence,
    _compute_encounter_confidence,
    _jaccard_tokens,
    align_extractions,
)


class TestJaccardTokens:
    def test_identical(self):
        assert _jaccard_tokens("chest pain", "chest pain") == 1.0

    def test_no_overlap(self):
        assert _jaccard_tokens("chest pain", "diabetes mellitus") == 0.0

    def test_partial_overlap(self):
        score = _jaccard_tokens("lower back pain", "back pain")
        assert 0.5 < score < 1.0

    def test_empty(self):
        assert _jaccard_tokens("", "hello") == 0.0


class TestEntityConfidence:
    def test_full_agreement(self):
        entity = AlignedEntity(
            sentence_id="s0",
            snomed_concept_id="123",
            snomed_term="test",
            text="test",
            lookup_term="test",
            semantic_tag="disorder",
            assertion="present",
            extraction_agreement=1.0,
            coding_margin=1.0,
            disambiguation_agreement=1.0,
            read_code_corroboration=1.0,
        )
        score = _compute_entity_confidence(entity)
        assert score == pytest.approx(1.0)

    def test_partial_agreement(self):
        entity = AlignedEntity(
            sentence_id="s0",
            snomed_concept_id="123",
            snomed_term="test",
            text="test",
            lookup_term="test",
            semantic_tag="disorder",
            assertion="present",
            extraction_agreement=0.67,
            coding_margin=0.85,
            disambiguation_agreement=0.67,
            read_code_corroboration=0.0,
        )
        score = _compute_entity_confidence(entity)
        assert 0.4 < score < 0.7

    def test_read_code_boost(self):
        entity = AlignedEntity(
            sentence_id="s0",
            snomed_concept_id="123",
            snomed_term="test",
            text="test",
            lookup_term="test",
            semantic_tag="disorder",
            assertion="present",
            extraction_agreement=1.0,
            coding_margin=0.9,
            disambiguation_agreement=1.0,
            read_code_corroboration=0.0,
        )
        without_read = _compute_entity_confidence(entity, has_inline_read_code=False)
        with_read = _compute_entity_confidence(entity, has_inline_read_code=True)
        assert with_read > without_read


class TestEncounterConfidence:
    def test_empty(self):
        assert _compute_encounter_confidence([]) == 0.0

    def test_single_entity(self):
        e = AlignedEntity(
            sentence_id="s0", snomed_concept_id="1", snomed_term="x",
            text="x", lookup_term="x", semantic_tag="disorder",
            assertion="present", consensus_confidence=0.8,
        )
        assert _compute_encounter_confidence([e]) == 0.8


class TestAlignExtractions:
    def test_simple_consensus(self):
        model_a = {"terms": [
            {
                "sentence_id": "s0",
                "text": "hypertension",
                "lookup_term": "hypertension",
                "semantic_tag": "disorder",
                "assertion": "present",
                "coding": {"snomed_concept_id": "38341003", "snomed_term": "Hypertension", "score": 0.95},
            }
        ]}
        model_b = {"terms": [
            {
                "sentence_id": "s0",
                "text": "HTN",
                "lookup_term": "hypertension",
                "semantic_tag": "disorder",
                "assertion": "present",
                "coding": {"snomed_concept_id": "38341003", "snomed_term": "Hypertension", "score": 0.92},
            }
        ]}

        result = align_extractions([model_a, model_b], encounter_id="enc1", model_ids=["haiku", "gpt5"])
        assert isinstance(result, ConsensusResult)
        assert len(result.aligned_entities) == 1
        entity = result.aligned_entities[0]
        assert entity.snomed_concept_id == "38341003"
        assert entity.model_count == 2
        assert entity.extraction_agreement == 1.0

    def test_disagreement(self):
        model_a = {"terms": [
            {
                "sentence_id": "s0",
                "text": "chest pain",
                "lookup_term": "chest pain",
                "semantic_tag": "finding",
                "assertion": "present",
                "coding": {"snomed_concept_id": "29857009", "score": 0.9},
            }
        ]}
        model_b = {"terms": []}

        result = align_extractions([model_a, model_b], encounter_id="enc2")
        assert len(result.aligned_entities) == 1
        entity = result.aligned_entities[0]
        assert entity.extraction_agreement == 0.5

    def test_three_models(self):
        term = {
            "sentence_id": "s0",
            "text": "diabetes",
            "lookup_term": "diabetes mellitus",
            "semantic_tag": "disorder",
            "assertion": "present",
            "coding": {"snomed_concept_id": "73211009", "score": 0.9},
        }
        results = [{"terms": [term]}, {"terms": [term]}, {"terms": [term]}]
        result = align_extractions(results, encounter_id="enc3")
        assert len(result.aligned_entities) == 1
        assert result.aligned_entities[0].extraction_agreement == 1.0
