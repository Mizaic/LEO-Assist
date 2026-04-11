"""Tests: extractor backend selection and fallback behaviour.

Covers:
- build_extractor() returns correct provider per CODING_EXTRACTOR_BACKEND.
- strict=false: model failure falls back to LLM with fallback_used event.
- strict=true: model failure raises RuntimeError.
- auto mode: selects model when available, falls back to llm when not.
- FallbackExtractor emits progress hook events on fallback.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.coding_worker.app.pipeline.extractor_contract import (
    ExtractionItem,
    CONTRACT_VERSION,
)

# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------


def _make_stub(source="stub", available=True, raises=None):
    provider = MagicMock()
    provider.source = source
    provider.model_name = f"{source}-model"
    provider.model_version = "1.0"
    provider.is_available.return_value = available
    if raises:
        provider.extract_batch.side_effect = raises
    else:
        provider.extract_batch.return_value = [
            ExtractionItem(
                sentence_id="s1",
                text="cancer",
                span_start=0,
                span_end=6,
                semantic_tag="disease",
                assertion="present",
                confidence=0.9,
                normalized="cancer",
                source=source,
                model_name=f"{source}-model",
                model_version="1.0",
                contract_version=CONTRACT_VERSION,
            )
        ]
    return provider


# ---------------------------------------------------------------------------
# Backend env selection
# ---------------------------------------------------------------------------


def test_build_extractor_llm_backend(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "llm")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "false")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    llm_stub = _make_stub("llm")

    with patch.object(reg, "_make_llm_provider", return_value=llm_stub):
        provider = reg.build_extractor()

    assert provider.source == "llm"


def test_build_extractor_model_backend_available(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "model")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "false")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=True)
    llm_stub = _make_stub("llm")

    with (
        patch.object(reg, "_make_model_provider", return_value=model_stub),
        patch.object(reg, "_make_llm_provider", return_value=llm_stub),
    ):
        provider = reg.build_extractor()

    # Should be FallbackExtractor wrapping model as primary
    assert provider.source == "model"


def test_build_extractor_model_backend_unavailable_non_strict(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "model")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "false")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=False)
    llm_stub = _make_stub("llm")

    with (
        patch.object(reg, "_make_model_provider", return_value=model_stub),
        patch.object(reg, "_make_llm_provider", return_value=llm_stub),
    ):
        provider = reg.build_extractor()

    # Falls back to llm when model unavailable (non-strict)
    assert provider.source == "llm"


def test_build_extractor_model_backend_unavailable_strict(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "model")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "true")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=False)

    with patch.object(reg, "_make_model_provider", return_value=model_stub):
        with pytest.raises(RuntimeError, match="unavailable"):
            reg.build_extractor()


def test_build_extractor_auto_prefers_model(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "auto")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "false")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=True)
    llm_stub = _make_stub("llm")

    with (
        patch.object(reg, "_make_model_provider", return_value=model_stub),
        patch.object(reg, "_make_llm_provider", return_value=llm_stub),
    ):
        provider = reg.build_extractor()

    assert provider.source == "model"


def test_build_extractor_auto_falls_back_to_llm(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "auto")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "false")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=False)
    llm_stub = _make_stub("llm")

    with (
        patch.object(reg, "_make_model_provider", return_value=model_stub),
        patch.object(reg, "_make_llm_provider", return_value=llm_stub),
    ):
        provider = reg.build_extractor()

    assert provider.source == "llm"


# ---------------------------------------------------------------------------
# FallbackExtractor runtime fallback
# ---------------------------------------------------------------------------


def test_fallback_extractor_emits_progress_event(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "model")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "false")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=True, raises=RuntimeError("timeout"))
    llm_stub = _make_stub("llm")

    events: list[dict[str, Any]] = []

    with (
        patch.object(reg, "_make_model_provider", return_value=model_stub),
        patch.object(reg, "_make_llm_provider", return_value=llm_stub),
    ):
        provider = reg.build_extractor(progress_hook=events.append)

    # Trigger extraction — model raises, should fall back to llm
    result = provider.extract_batch("encounter text", [])

    # llm stub returns one item
    assert len(result) == 1
    assert result[0].source == "llm"

    # fallback_used event must have been emitted
    fb_events = [e for e in events if e.get("type") == "fallback_used"]
    assert len(fb_events) == 1
    assert fb_events[0]["primary_backend"] == "model"
    assert fb_events[0]["fallback_backend"] == "llm"


def test_fallback_extractor_strict_raises(monkeypatch):
    monkeypatch.setenv("CODING_EXTRACTOR_BACKEND", "model")
    monkeypatch.setenv("CODING_EXTRACTOR_STRICT", "true")

    from services.coding_worker.app.pipeline import extractor_registry as reg

    model_stub = _make_stub("model", available=True, raises=RuntimeError("down"))
    llm_stub = _make_stub("llm")

    with (
        patch.object(reg, "_make_model_provider", return_value=model_stub),
        patch.object(reg, "_make_llm_provider", return_value=llm_stub),
    ):
        provider = reg.build_extractor()

    with pytest.raises(RuntimeError):
        provider.extract_batch("text", [])
