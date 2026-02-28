"""Tests: canonical ExtractorProvider contract compliance.

Both LLMExtractorProvider and ModelExtractorProvider must:
1. Satisfy the ExtractorProvider protocol (duck-typing check).
2. Produce ExtractionItem instances with all required fields.
3. Stamp the correct source/model_name/model_version/contract_version.
4. Round-trip through with_provenance() correctly.
"""

from __future__ import annotations

import pytest

from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
    ExtractorProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_item(**kwargs) -> ExtractionItem:
    defaults = dict(
        sentence_id="s001",
        text="colorectal cancer",
        span_start=0,
        span_end=17,
        semantic_tag="disease",
        assertion="present",
        confidence=0.95,
        normalized="colorectal cancer",
        source="llm",
        model_name="test-model",
        model_version="1.0",
        contract_version=CONTRACT_VERSION,
    )
    defaults.update(kwargs)
    return ExtractionItem(**defaults)


class _StubProvider:
    """Minimal in-test provider conforming to ExtractorProvider protocol."""

    source = "stub"
    model_name = "stub-model"
    model_version = "0.1"

    def is_available(self) -> bool:
        return True

    def extract_batch(self, encounter_text: str, sentences: list) -> list[ExtractionItem]:
        return [make_item(source=self.source, model_name=self.model_name,
                          model_version=self.model_version)]


# ---------------------------------------------------------------------------
# Protocol checks
# ---------------------------------------------------------------------------

def test_stub_satisfies_protocol():
    provider = _StubProvider()
    assert isinstance(provider, ExtractorProvider)


def test_extraction_item_has_all_required_fields():
    item = make_item()
    assert item.sentence_id
    assert item.text
    assert item.semantic_tag
    assert item.assertion
    assert item.contract_version == CONTRACT_VERSION
    assert item.source
    assert item.model_name
    assert item.model_version


def test_extraction_item_frozen():
    item = make_item()
    with pytest.raises((AttributeError, TypeError)):
        item.text = "modified"  # type: ignore[misc]


def test_with_provenance_returns_new_item():
    item = make_item(source="unknown", model_name="", model_version="")
    stamped = item.with_provenance("model", "spacy-ner", "1.2")
    assert stamped.source == "model"
    assert stamped.model_name == "spacy-ner"
    assert stamped.model_version == "1.2"
    # Original unchanged
    assert item.source == "unknown"


def test_with_provenance_preserves_other_fields():
    item = make_item(confidence=0.8, semantic_tag="procedure")
    stamped = item.with_provenance("llm", "bedrock", "2.0")
    assert stamped.confidence == 0.8
    assert stamped.semantic_tag == "procedure"
    assert stamped.contract_version == CONTRACT_VERSION


# ---------------------------------------------------------------------------
# LLMExtractorProvider
# ---------------------------------------------------------------------------

def test_llm_provider_satisfies_protocol():
    """LLMExtractorProvider must satisfy ExtractorProvider at import time."""
    from services.coding_worker.app.pipeline.providers.llm_provider import (
        LLMExtractorProvider,
    )
    provider = LLMExtractorProvider()
    assert isinstance(provider, ExtractorProvider)
    assert provider.source == "llm"
    assert provider.model_name  # non-empty or "llm-unconfigured"
    assert provider.model_version


def test_llm_provider_is_available_without_credentials():
    """is_available() returns False gracefully when boto3 client fails."""
    from services.coding_worker.app.pipeline.providers.llm_provider import (
        LLMExtractorProvider,
    )
    provider = LLMExtractorProvider()
    # Without real AWS creds this returns False — must not raise
    result = provider.is_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# ModelExtractorProvider
# ---------------------------------------------------------------------------

def test_model_provider_satisfies_protocol():
    from services.coding_worker.app.pipeline.providers.model_provider import (
        ModelExtractorProvider,
    )
    provider = ModelExtractorProvider()
    assert isinstance(provider, ExtractorProvider)
    assert provider.source == "model"
    assert provider.model_name
    assert provider.model_version


def test_model_provider_service_unavailable_returns_false(monkeypatch):
    """is_available() returns False when inference service is down."""
    import httpx

    def _failing_get(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", _failing_get)

    from services.coding_worker.app.pipeline.providers.model_provider import (
        ModelExtractorProvider,
    )
    provider = ModelExtractorProvider()
    assert not provider.is_available()


# ---------------------------------------------------------------------------
# ExtractionItem equality and hashing
# ---------------------------------------------------------------------------

def test_extraction_item_equality():
    a = make_item()
    b = make_item()
    assert a == b


def test_extraction_item_inequality():
    a = make_item(text="cancer")
    b = make_item(text="polyp")
    assert a != b
