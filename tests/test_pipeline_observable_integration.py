"""Integration test: observable post-processing flows through the unified pipeline."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from libs.pipeline.post_processing import run_post_processing
from services.coding_worker.app.pipeline.extractor_contract import ExtractionItem
from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk

pytestmark = pytest.mark.skip(
    reason="Legacy CodingPipeline observable integration test skipped after WorkflowEngine cutover."
)


class _ExtractorStub:
    source = "model"
    model_name = "test-model"
    model_version = "test-v1"


def test_pipeline_observable_post_processing_flows_into_payload() -> None:
    encounter_text = "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]"
    sentence = SentenceChunk(
        sentence_id="s0",
        text=encounter_text,
        start=0,
        end=len(encounter_text),
    )
    item = ExtractionItem(
        sentence_id="s0",
        text=encounter_text,
        span_start=0,
        span_end=len(encounter_text),
        semantic_tag="observable_entity",
        assertion="present",
        confidence=0.98,
        normalized=encounter_text,
        source="model",
        model_name="test-model",
        model_version="test-v1",
    )

    entity_dicts = _items_to_dicts([item])
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        processed = run_post_processing(encounter_text, entity_dicts)

    obs = [e for e in processed if e["label"] == "observable_entity"]
    assert len(obs) >= 1
    assert obs[0]["text"] == "Neutrophil count"
    assert obs[0].get("value") == "2.41"
    assert obs[0].get("unit") == "10^9/L"
    assert obs[0].get("reference_range") == "1.5 - 7.5"

    result_item = _dict_to_item(obs[0])
    assert result_item.text == "Neutrophil count"
    assert result_item.numeric_value == "2.41"
    assert result_item.unit == "10^9/L"
    assert result_item.reference_range == "1.5 - 7.5"

    extracted = {"s0": [result_item]}
    resolved = {
        "Neutrophil count": [
            {
                "snomed_concept_id": "123456",
                "read_code": "42J..",
                "snomed_term": "Neutrophil count",
                "score": 0.99,
            }
        ]
    }
    pipeline = CodingPipeline(patient_client=None, knowledge_client=None)
    payload = pipeline._build_sentences_payload(
        [sentence], extracted, resolved, _ExtractorStub()
    )
    term = payload[0]["terms"][0]
    assert term["text"] == "Neutrophil count"
    assert term["numeric_value"] == "2.41"
    assert term["unit"] == "10^9/L"
    assert term["reference_range"] == "1.5 - 7.5"
    assert term["coding"]["snomed_concept_id"] == "123456"


def test_pipeline_preserves_provider_normalized_lookup_term_when_custom() -> None:
    encounter_text = "Urine albumin level (XE2eI) 9 mg/L [< 15]"
    item = ExtractionItem(
        sentence_id="s0",
        text=encounter_text,
        span_start=0,
        span_end=len(encounter_text),
        semantic_tag="observable_entity",
        assertion="present",
        confidence=0.95,
        normalized="urine albumin",
        source="model",
        model_name="test-model",
        model_version="test-v1",
    )

    entity_dicts = _items_to_dicts([item])
    with patch("libs.pipeline.post_processing.apply_context_detection_to_dicts"):
        processed = run_post_processing(encounter_text, entity_dicts)

    obs = [e for e in processed if e["label"] == "observable_entity"]
    assert len(obs) >= 1
    result_item = _dict_to_item(obs[0])
    assert result_item.normalized == "urine albumin"
