from __future__ import annotations

from services.coding_worker.app.pipeline.extractor_contract import ExtractionItem
from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline
from services.coding_worker.app.pipeline.sentence_splitter import SentenceChunk


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
    extracted = {
        "s0": [
            ExtractionItem(
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
        ]
    }

    pipeline = CodingPipeline(patient_client=None, knowledge_client=None)

    normalized = pipeline._apply_observable_post_processing(encounter_text, extracted)
    item = normalized["s0"][0]
    assert item.text == "Neutrophil count"
    assert item.span_start == 0
    assert item.span_end == len("Neutrophil count")
    assert item.numeric_value == "2.41"
    assert item.unit == "10^9/L"
    assert item.reference_range == "1.5 - 7.5"
    assert item.normalized == "Neutrophil count"

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
    payload = pipeline._build_sentences_payload([sentence], normalized, resolved, _ExtractorStub())
    term = payload[0]["terms"][0]
    assert term["text"] == "Neutrophil count"
    assert term["numeric_value"] == "2.41"
    assert term["unit"] == "10^9/L"
    assert term["reference_range"] == "1.5 - 7.5"
    assert term["coding"]["snomed_concept_id"] == "123456"


def test_pipeline_preserves_provider_normalized_lookup_term_when_custom() -> None:
    encounter_text = "Urine albumin level (XE2eI) 9 mg/L [< 15]"
    sentence = SentenceChunk(sentence_id="s0", text=encounter_text, start=0, end=len(encounter_text))
    extracted = {
        "s0": [
            ExtractionItem(
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
        ]
    }
    pipeline = CodingPipeline(patient_client=None, knowledge_client=None)
    normalized = pipeline._apply_observable_post_processing(encounter_text, extracted)
    assert normalized["s0"][0].normalized == "urine albumin"
