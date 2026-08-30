"""Tests for suspected-cancer guard against confirmed malignancy miscoding."""

from __future__ import annotations

from unittest.mock import patch

from libs.ner.suspected_cancer_guard import (
    dedupe_suspected_malignancy_conflicts,
    enrich_suspected_cancer_lookup,
    guard_suspected_cancer_resolution,
    is_suspected_cancer_context,
)
from libs.pipeline.post_processing import run_post_processing_with_trace
from libs.pipeline_graph.subgraphs.terminology import (
    _resolve_lookup_term,
    _resolve_terms,
)
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.terminology.client import ResolvedTerm


def test_is_suspected_cancer_context_for_assessment_phrase() -> None:
    assert is_suspected_cancer_context(
        "oesophageal cancer",
        "Refer for endoscopy to assess for oesophageal cancer.",
    )


def test_enrich_does_not_rewrite_taught_checkbox_breast_pain() -> None:
    """A taught pain tick is a finding. 2WW chrome must not recode it."""
    encounter = (
        "Refer under the suspected cancer pathway for "
        "Intractable breast pain not responding to NSAID [X]"
    )
    start = encounter.find("Intractable breast pain")
    entity = {
        "text": "Intractable breast pain",
        "lookup_term": "Intractable breast pain",
        "label": "finding",
        "semantic_tag": "finding",
        "start": start,
        "end": start + len("Intractable breast pain"),
        "__source": "form_schema_checkbox",
    }
    enrich_suspected_cancer_lookup(entity, encounter)
    assert entity["lookup_term"] == "Intractable breast pain"
    assert entity["label"] == "finding"
    assert entity.get("_suspected_cancer_guard") is None


def test_enrich_lookup_sets_upper_gi_suspected() -> None:
    entity = {
        "label": "situation",
        "text": "oesophageal cancer",
        "start": 40,
        "end": 58,
        "lookup_term": "oesophageal cancer",
    }
    encounter = (
        "I am referring James urgently via the suspected cancer pathway "
        "for assessment of oesophageal cancer."
    )
    enrich_suspected_cancer_lookup(entity, encounter)
    assert "upper gastrointestinal tract suspected" in entity["lookup_term"].lower()
    assert entity.get("_suspected_cancer_guard") == "enriched_lookup"


def test_resolve_lookup_term_prefers_suspected_normalized() -> None:
    entity = {
        "text": "oesophageal cancer",
        "lookup_term": "oesophageal cancer",
        "normalized": "malignant neoplasm of upper gastrointestinal tract suspected",
    }
    assert "suspected" in _resolve_lookup_term(entity).lower()


def test_guard_remaps_confirmed_malignancy_disorder() -> None:
    entity = {
        "label": "situation",
        "text": "oesophageal cancer",
        "lookup_term": "oesophageal cancer",
        "concept_id": "363402007",
        "term": "Malignant neoplasm of esophagus (disorder)",
        "semantic_tag": "disorder",
        "start": 60,
        "end": 78,
    }
    encounter = (
        "I am referring James urgently via the suspected cancer pathway "
        "for assessment of oesophageal cancer."
    )
    guard_suspected_cancer_resolution(entity, encounter)
    assert entity["concept_id"] == "315273002"
    assert entity["semantic_tag"] == "situation"
    assert entity.get("_suspected_cancer_guard") == "remapped_disorder_to_situation"


def test_dedupe_drops_disorder_when_suspected_situation_present() -> None:
    entities = [
        {
            "__sentence_id": "s0",
            "label": "situation",
            "text": "suspected cancer pathway",
            "concept_id": "162572001",
            "semantic_tag": "situation",
            "term": "Malignant neoplastic disease suspected (situation)",
        },
        {
            "__sentence_id": "s0",
            "label": "situation",
            "text": "oesophageal cancer",
            "concept_id": "363402007",
            "semantic_tag": "disorder",
            "term": "Malignant neoplasm of esophagus (disorder)",
        },
    ]
    kept = dedupe_suspected_malignancy_conflicts(entities)
    concept_ids = {entity["concept_id"] for entity in kept}
    assert "363402007" not in concept_ids
    assert "162572001" in concept_ids


@patch("libs.pipeline_graph.subgraphs.terminology.TerminologyClient")
def test_resolve_terms_applies_suspected_cancer_guard(mock_client) -> None:
    mock_client.return_value.resolve.return_value = {
        "Malignant neoplasm of upper gastrointestinal tract suspected": [
            ResolvedTerm(
                text="Malignant neoplasm of upper gastrointestinal tract suspected",
                concept_id="363402007",
                term="Malignant neoplasm of esophagus (disorder)",
                semantic_tag="disorder",
                score=1.0,
            )
        ]
    }
    entities = [
        {
            "label": "situation",
            "text": "oesophageal cancer",
            "lookup_term": "oesophageal cancer",
            "start": 60,
            "end": 78,
        }
    ]
    encounter = (
        "I am referring James urgently via the suspected cancer pathway "
        "for assessment of oesophageal cancer."
    )
    result = _resolve_terms(
        {
            "entities": entities,
            "encounter_text": encounter,
            "expected_tags": {},
        }
    )
    resolved = result["resolved_entities"][0]
    assert resolved["concept_id"] == "315273002"
    assert resolved["semantic_tag"] == "situation"


def test_post_processing_runs_suspected_cancer_layer() -> None:
    encounter = "Refer under suspected cancer pathway for stomach cancer."
    entities = [
        {
            "label": "situation",
            "text": "suspected cancer pathway for stomach cancer",
            "start": 12,
            "end": 55,
        }
    ]
    _, trace = run_post_processing_with_trace(
        encounter, entities, enable_disorder_gate=False
    )
    layer_ids = [layer["layer_id"] for layer in trace]
    assert "layer_8b" in layer_ids


def test_extraction_examples_include_oesophageal_suspected_pathway() -> None:
    example = next(
        ex
        for ex in EXTRACTION_EXAMPLES
        if ex.get("description")
        == "Upper GI oesophageal 2WW -- one situation span only"
    )
    assert "oesophageal cancer" in example["input"]
    assert "upper gastrointestinal tract suspected" in example["output"]


def test_extraction_prompt_documents_assessment_phrases() -> None:
    assert "assessment of oesophageal cancer" in EXTRACTION_SYSTEM_V1
    assert "exclude malignancy" in EXTRACTION_SYSTEM_V1
