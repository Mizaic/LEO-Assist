from __future__ import annotations

import os
from typing import Any, Callable

from services.coding_worker.app.pipeline.providers.llm_provider import LLMExtractorProvider
from services.coding_worker.app.pipeline.providers.model_provider import ModelExtractorProvider


def _make_llm_provider():
    return LLMExtractorProvider()


def _make_model_provider():
    return ModelExtractorProvider()


class FallbackExtractor:
    def __init__(
        self,
        primary,
        fallback,
        *,
        strict: bool,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._strict = strict
        self._progress_hook = progress_hook
        self.source = getattr(primary, "source", "")
        self.model_name = getattr(primary, "model_name", "")
        self.model_version = getattr(primary, "model_version", "")

    def is_available(self) -> bool:
        return bool(self._primary.is_available())

    def extract_batch(self, encounter_text: str, sentences: list):
        try:
            return self._primary.extract_batch(encounter_text, sentences)
        except Exception:
            if self._strict:
                raise
            if self._progress_hook:
                self._progress_hook(
                    {
                        "type": "fallback_used",
                        "primary_backend": getattr(self._primary, "source", ""),
                        "fallback_backend": getattr(self._fallback, "source", ""),
                    }
                )
            return self._fallback.extract_batch(encounter_text, sentences)


def build_extractor(progress_hook: Callable[[dict[str, Any]], None] | None = None):
    backend = os.getenv("CODING_EXTRACTOR_BACKEND", "auto").lower()
    strict = os.getenv("CODING_EXTRACTOR_STRICT", "false").lower() == "true"
    llm = _make_llm_provider()
    model = _make_model_provider()

    if backend == "llm":
        return llm
    if backend == "model":
        if not model.is_available():
            if strict:
                raise RuntimeError("model backend unavailable")
            return llm
        return FallbackExtractor(model, llm, strict=strict, progress_hook=progress_hook)
    if backend == "auto":
        if model.is_available():
            return FallbackExtractor(model, llm, strict=strict, progress_hook=progress_hook)
        return llm
    return llm
