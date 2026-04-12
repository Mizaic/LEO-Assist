from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.coding_worker.app.pipeline.providers.model_provider import (
    ModelExtractorProvider,
)


def test_health_url_defaults_to_8004(monkeypatch):
    monkeypatch.delenv("MODEL_INFERENCE_HEALTH_URL", raising=False)
    monkeypatch.delenv("CODING_MODEL_PROVIDER_ENABLED", raising=False)
    provider = ModelExtractorProvider()
    assert provider._health_url == "http://localhost:8004/health"
    assert provider._enabled is True


def test_extract_batch_maps_entities(monkeypatch):
    monkeypatch.setenv("CODING_MODEL_PROVIDER_ENABLED", "true")

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model_name": "model-inference",
                "model_version": "v1",
                "entities": [
                    {
                        "sentence_id": "s0",
                        "text": "hypertension",
                        "label": "disorder",
                        "semantic_tag": "disorder",
                        "span_start": 5,
                        "span_end": 17,
                        "confidence": 0.91,
                        "normalized": "hypertension",
                        "source_meta": {"model_label": "DISORDER"},
                    }
                ],
            }

    class _Client:
        def __init__(self, timeout: float):
            self.timeout = timeout
            self.payload = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, json: dict):
            assert url == "http://localhost:8004/extract"
            self.payload = json
            assert self.payload["sentences"][0]["sentence_id"] == "s0"
            return _Resp()

    monkeypatch.setattr(
        "services.coding_worker.app.pipeline.providers.model_provider.httpx.Client",
        _Client,
    )
    provider = ModelExtractorProvider()
    sentences = [
        SimpleNamespace(sentence_id="s0", text="has hypertension", start=0, end=16)
    ]
    items = provider.extract_batch("Patient has hypertension", sentences)
    assert len(items) == 1
    assert items[0].text == "hypertension"
    assert items[0].semantic_tag == "disorder"
    assert items[0].source == "model"
    assert items[0].model_version == "v1"


def test_extract_batch_falls_back_to_llm_when_disabled(monkeypatch):
    monkeypatch.setenv("CODING_MODEL_PROVIDER_ENABLED", "false")
    called = {"value": False}

    class _FallbackExtractor:
        def extract_batch(self, encounter_text, sentences):
            called["value"] = True
            assert encounter_text == "text"
            assert sentences == []
            return []

    monkeypatch.setattr(
        ModelExtractorProvider,
        "_build_fallback_extractor",
        staticmethod(lambda: _FallbackExtractor()),
    )
    provider = ModelExtractorProvider()
    assert provider.extract_batch("text", []) == []
    assert called["value"] is True
