from __future__ import annotations

import pytest

pytest.importorskip("langgraph.graph")

from libs.ner.extractor_contract import ExtractionItem
from libs.pipeline_graph.subgraphs.extraction import extract_entities


def test_extract_entities_uses_ner_provider_when_requested(monkeypatch):
    class _Provider:
        def extract_batch(self, encounter_text, chunks):
            assert encounter_text == "Patient has asthma."
            assert len(chunks) == 1
            return [
                ExtractionItem(
                    sentence_id="s0",
                    text="asthma",
                    span_start=12,
                    span_end=18,
                    semantic_tag="disorder",
                    assertion="present",
                    confidence=0.9,
                    normalized="asthma",
                    source="model",
                    model_name="model-inference",
                    model_version="v1",
                )
            ]

    monkeypatch.setattr(
        "services.coding_worker.app.pipeline.providers.model_provider.ModelExtractorProvider",
        _Provider,
    )

    result = extract_entities(
        {
            "encounter_text": "Patient has asthma.",
            "extraction_method": "ner",
            "sentences": [{"sentence_id": "s0", "text": "Patient has asthma.", "start": 0, "end": 19}],
        }
    )
    assert len(result["entities"]) == 1
    assert result["entities"][0]["text"] == "asthma"
    assert result["llm_tokens"]["input_tokens"] == 0
